import asyncio
import json

import httpx
import openai
import pytest
from asgiref.sync import async_to_sync, sync_to_async

from apps.agents.services.schemas import RoutingDecision
from apps.llm.models import AgentModelConfig
from apps.llm.services.factory import AudioClient
from apps.progress.models import Attempt
from apps.usage.models import LiveSessionLease
from apps.voice import consumers as voice_consumers
from apps.voice.services.pcm_stream import PcmFormat
from apps.voice.services import tts
from apps.voice.tests.round_shapes import (
    END_SESSION,
    STUDENT_TEXT,
    connect,
    install,
    student_token,
)
from apps.voice.tests.test_pcm_stream import pcm, split, wav_header
from apps.voice.tests.test_tts_stream import _FakeGroqClient, _FakeStreamingSpeech

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

_OPENING = "Hello, let's talk about the deadline."
_PASSING = "That one is for Tom."
_RECEIVING = "Sure. What is still missing on the export?"
_REDIRECT = RoutingDecision(speaker="rachel", topic_owner="tom")
_REQUEST = httpx.Request("POST", "https://provider.example/v1/audio/speech")
_PIECE = 10


class FakeSpeechStream:
    """Fluxo de fala de mentira: o áudio é o texto em bytes, em pedaços de tamanho fixo."""

    def __init__(self, text: str, *, fail_after: int | None = None, sample_rate: int = 24000):
        raw = text.encode()
        self._chunks = [raw[start : start + _PIECE] for start in range(0, len(raw), _PIECE)]
        self._fail_after = fail_after
        self.format = PcmFormat(sample_rate=sample_rate, channels=1)
        self.total_bytes = 0

    def __iter__(self):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index == self._fail_after:
                raise openai.APIConnectionError(request=_REQUEST)
            self.total_bytes += len(chunk)
            yield chunk


def _stream_with(monkeypatch, **options) -> list[str]:
    """Troca a síntese em fluxo pelo falso e devolve a lista dos textos pedidos."""
    requested: list[str] = []

    def synthesize_stream(text, voice):
        requested.append(text)
        return FakeSpeechStream(text, **options)

    monkeypatch.setattr(voice_consumers, "synthesize_stream", synthesize_stream)
    return requested


async def _let_the_opening_settle() -> None:
    """Dá à sessão o instante de marcar a abertura como concluída antes da próxima mensagem.

    O servidor ignora a fala do aluno que chega antes disso, e um cliente de verdade só fala
    depois de tocar a abertura, o que leva segundos. O teste, que responde na hora, espera.
    """
    await asyncio.sleep(0.1)


async def _read_line(communicator) -> dict:
    """Lê uma fala em fluxo: o nome, o início, os pedaços e o fim, ou até o erro."""
    line: dict = {"chunks": [], "start": None, "end": None, "error": None}
    while True:
        raw = await communicator.receive_from()
        if isinstance(raw, bytes):
            line["chunks"].append(raw)
            continue
        message = json.loads(raw)
        if message["type"] == "speaker":
            line["speaker"] = message["name"]
        elif message["type"] == "speech_start":
            line["start"] = message
        elif message["type"] == "speech_end":
            line["end"] = message
            return line
        elif message["type"] == "error":
            line["error"] = message
            return line
        else:
            raise AssertionError(f"mensagem inesperada: {message}")


def _spoken(line: dict) -> str:
    return b"".join(line["chunks"]).decode()


def test_the_opening_is_sent_as_start_chunks_and_end(django_user_model, monkeypatch):
    install(monkeypatch, [_OPENING], RoutingDecision(speaker="none", topic_owner="none"))
    requested = _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> dict:
        communicator = await connect(token, stream_audio=True)
        line = await _read_line(communicator)
        await communicator.disconnect()
        return line

    line = async_to_sync(run)()

    assert requested == [_OPENING]
    assert line["speaker"] == "Rachel"
    assert line["start"] == {
        "type": "speech_start",
        "format": "pcm_s16le",
        "sample_rate": 24000,
        "channels": 1,
    }
    assert len(line["chunks"]) > 1
    assert _spoken(line) == _OPENING
    assert line["end"] == {"type": "speech_end", "bytes": len(_OPENING.encode())}


def test_a_round_of_two_lines_streams_each_one_in_order(django_user_model, monkeypatch):
    install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT)
    _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> list[dict]:
        communicator = await connect(token, stream_audio=True)
        await _read_line(communicator)
        await _let_the_opening_settle()
        await communicator.send_to(bytes_data=b"student-audio")
        lines = [await _read_line(communicator), await _read_line(communicator)]
        await communicator.disconnect()
        return lines

    first, second = async_to_sync(run)()

    assert (first["speaker"], _spoken(first)) == ("Rachel", _PASSING)
    assert (second["speaker"], _spoken(second)) == ("Tom", _RECEIVING)
    assert first["end"]["bytes"] == len(_PASSING.encode())
    assert second["end"]["bytes"] == len(_RECEIVING.encode())


def test_the_session_still_reaches_the_attempt_with_the_same_conversation(
    django_user_model, monkeypatch
):
    installed = install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT)
    _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> None:
        communicator = await connect(token, stream_audio=True)
        await _read_line(communicator)
        await _let_the_opening_settle()
        await communicator.send_to(bytes_data=b"student-audio")
        await _read_line(communicator)
        await _read_line(communicator)
        await communicator.send_to(text_data=END_SESSION)
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        await communicator.disconnect()

    async_to_sync(run)()

    assert installed.evaluated == [
        [f"[Rachel] {_OPENING}", STUDENT_TEXT, f"[Rachel] {_PASSING}", f"[Tom] {_RECEIVING}"]
    ]
    assert installed.synthesized == []


def test_with_the_server_switch_off_the_whole_line_is_sent_as_before(
    django_user_model, monkeypatch, settings
):
    settings.STREAM_PERSONA_SPEECH = False
    install(monkeypatch, [_OPENING], RoutingDecision(speaker="none", topic_owner="none"))
    requested = _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> tuple[dict, bytes]:
        communicator = await connect(token, stream_audio=True)
        speaker = json.loads(await communicator.receive_from())
        audio = await communicator.receive_from()
        await communicator.disconnect()
        return speaker, audio

    speaker, audio = async_to_sync(run)()

    assert speaker == {"type": "speaker", "name": "Rachel"}
    assert audio == _OPENING.encode()
    assert requested == []


def test_a_client_that_did_not_declare_support_never_gets_the_stream(
    django_user_model, monkeypatch
):
    install(monkeypatch, [_OPENING], RoutingDecision(speaker="none", topic_owner="none"))
    requested = _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> tuple[dict, bytes]:
        communicator = await connect(token)
        await communicator.send_to(
            text_data=json.dumps({"type": "stream_audio", "enabled": True})
        )
        speaker = json.loads(await communicator.receive_from())
        audio = await communicator.receive_from()
        await communicator.disconnect()
        return speaker, audio

    speaker, audio = async_to_sync(run)()

    assert speaker["type"] == "speaker"
    assert audio == _OPENING.encode()
    assert requested == []


def test_the_client_can_go_back_to_the_whole_line_for_the_next_ones(django_user_model, monkeypatch):
    install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT)
    requested = _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> tuple[dict, list]:
        communicator = await connect(token, stream_audio=True)
        opening = await _read_line(communicator)
        await communicator.send_to(
            text_data=json.dumps({"type": "stream_audio", "enabled": False})
        )
        await _let_the_opening_settle()
        await communicator.send_to(bytes_data=b"student-audio")
        frames = []
        for _ in range(4):
            raw = await communicator.receive_from()
            frames.append(raw if isinstance(raw, bytes) else json.loads(raw))
        await communicator.disconnect()
        return opening, frames

    opening, frames = async_to_sync(run)()

    assert _spoken(opening) == _OPENING
    assert frames == [
        {"type": "speaker", "name": "Rachel"},
        _PASSING.encode(),
        {"type": "speaker", "name": "Tom"},
        _RECEIVING.encode(),
    ]
    assert requested == [_OPENING]


def test_a_provider_failure_in_the_middle_ends_the_session_with_nothing_after_the_error(
    django_user_model, monkeypatch
):
    install(monkeypatch, [_OPENING], RoutingDecision(speaker="none", topic_owner="none"))
    _stream_with(monkeypatch, fail_after=2)
    token = student_token(django_user_model)

    async def run() -> tuple[list, int, bool]:
        communicator = await connect(token, stream_audio=True)
        frames = []
        while True:
            output = await communicator.receive_output()
            if output["type"] == "websocket.close":
                break
            if output.get("bytes") is not None:
                frames.append(("audio", output["bytes"]))
            else:
                frames.append(json.loads(output["text"]))
        await communicator.disconnect()
        leases = await sync_to_async(LiveSessionLease.objects.count)()
        open_attempt = await sync_to_async(lambda: Attempt.objects.get().completed_at is None)()
        return frames, leases, open_attempt

    frames, leases, open_attempt = async_to_sync(run)()

    assert frames[0] == {"type": "speaker", "name": "Rachel"}
    assert frames[1]["type"] == "speech_start"
    assert [frame[0] for frame in frames[2:4]] == ["audio", "audio"]
    assert frames[4]["type"] == "error"
    assert frames[4]["code"] == "provider_unavailable"
    assert len(frames) == 5
    assert not any(isinstance(frame, dict) and frame["type"] == "speech_end" for frame in frames)
    assert open_attempt
    assert leases == 0


def test_a_failure_before_any_audio_sends_no_start(django_user_model, monkeypatch):
    install(monkeypatch, [_OPENING], RoutingDecision(speaker="none", topic_owner="none"))
    _stream_with(monkeypatch, fail_after=0)
    token = student_token(django_user_model)

    async def run() -> list:
        communicator = await connect(token, stream_audio=True)
        frames = []
        while True:
            output = await communicator.receive_output()
            if output["type"] == "websocket.close":
                break
            frames.append(json.loads(output["text"]))
        await communicator.disconnect()
        return frames

    frames = async_to_sync(run)()

    assert [frame["type"] for frame in frames] == ["speaker", "error"]
    assert frames[1]["code"] == "provider_unavailable"


def test_the_notice_that_the_device_cannot_stream_is_not_lost_while_the_session_opens(
    django_user_model, monkeypatch
):
    install(monkeypatch, [_OPENING, _PASSING], RoutingDecision(speaker="none", topic_owner="none"))
    requested = _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> list:
        communicator = await connect(token, stream_audio=True)
        await communicator.send_to(
            text_data=json.dumps({"type": "stream_audio", "enabled": False})
        )
        frames = []
        for _ in range(2):
            raw = await communicator.receive_from()
            frames.append(raw if isinstance(raw, bytes) else json.loads(raw))
        await communicator.disconnect()
        return frames

    frames = async_to_sync(run)()

    assert frames == [{"type": "speaker", "name": "Rachel"}, _OPENING.encode()]
    assert requested == []


def test_the_real_stream_is_built_outside_the_event_loop_because_it_reads_the_database(
    django_user_model, monkeypatch
):
    install(monkeypatch, [_OPENING], RoutingDecision(speaker="none", topic_owner="none"))
    source = pcm(2000)
    speech = _FakeStreamingSpeech(split(wav_header() + source, [701, 1203, 999]))

    def audio_client_that_reads_the_database(purpose):
        AgentModelConfig.get_solo()
        return AudioClient(client=_FakeGroqClient(speech), model_id="tts-model")

    monkeypatch.setattr(tts, "get_audio_client", audio_client_that_reads_the_database)
    token = student_token(django_user_model)

    async def run() -> dict:
        communicator = await connect(token, stream_audio=True)
        line = await _read_line(communicator)
        await communicator.disconnect()
        return line

    line = async_to_sync(run)()

    assert line["error"] is None
    assert line["start"]["sample_rate"] == 24000
    assert b"".join(line["chunks"]) == source
    assert line["end"] == {"type": "speech_end", "bytes": len(source)}
