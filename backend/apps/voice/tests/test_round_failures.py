import json

import httpx
import openai
import pytest
from asgiref.sync import async_to_sync, sync_to_async

from apps.agents.services.schemas import RoutingDecision
from apps.progress.models import Attempt
from apps.usage.models import LiveSessionLease
from apps.voice.tests.round_shapes import connect, install, read_frames, speaker, student_token

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

_OPENING = "Hello, let's talk about the deadline."
_PASSING = "That one is for Tom."
_RECEIVING = "Sure. What is still missing on the export?"
_REDIRECT = RoutingDecision(speaker="rachel", topic_owner="tom")
_REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")


def _unreachable() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=_REQUEST)


def _failing_on(text: str):
    def synthesize(spoken, voice):
        if spoken == text:
            raise _unreachable()
        return spoken.encode()

    return synthesize


async def _everything_until_close(communicator) -> list:
    """Tudo o que o aluno recebe até a conexão fechar, na ordem, com os áudios como texto."""
    frames: list = []
    while True:
        output = await communicator.receive_output()
        if output["type"] == "websocket.close":
            return frames
        if output.get("bytes") is not None:
            frames.append(("audio", output["bytes"].decode()))
        else:
            frames.append(json.loads(output["text"]))


def _fail_in_the_round(monkeypatch, django_user_model, lines, synthesize=None):
    """Abre a sessão, responde uma vez e devolve o que chegou até a conexão fechar."""
    installed = install(monkeypatch, lines, _REDIRECT, synthesize=synthesize)
    token = student_token(django_user_model)

    async def run() -> tuple[list, int, bool]:
        communicator = await connect(token)
        await read_frames(communicator, 1)
        await communicator.send_to(bytes_data=b"student-audio")
        frames = await _everything_until_close(communicator)
        await communicator.disconnect()
        leases = await sync_to_async(LiveSessionLease.objects.count)()
        open_attempt = await sync_to_async(
            lambda: Attempt.objects.get().completed_at is None
        )()
        return frames, leases, open_attempt

    (frames, leases, open_attempt), synthesized = async_to_sync(run)(), installed.synthesized
    return frames, leases, open_attempt, synthesized


def _ends_with_only_the_error(frames: list, code: str) -> None:
    """O erro é o último quadro, vem uma única vez e leva o código esperado."""
    last = frames[-1]
    assert last["type"] == "error"
    assert last["code"] == code
    assert last["message"]
    assert not any(isinstance(frame, dict) and frame["type"] == "error" for frame in frames[:-1])


def test_the_model_failing_on_the_second_line_ends_the_session_with_nothing_after_the_error(
    django_user_model, monkeypatch
):
    frames, leases, open_attempt, _ = _fail_in_the_round(
        monkeypatch, django_user_model, [_OPENING, _PASSING, _unreachable()]
    )

    _ends_with_only_the_error(frames, "provider_unavailable")
    assert open_attempt
    assert leases == 0


def test_the_synthesis_failing_on_the_first_line_never_sends_nor_synthesizes_the_second(
    django_user_model, monkeypatch
):
    frames, leases, open_attempt, synthesized = _fail_in_the_round(
        monkeypatch,
        django_user_model,
        [_OPENING, _PASSING, _RECEIVING],
        synthesize=_failing_on(_PASSING),
    )

    assert frames[0] == speaker("Rachel")
    _ends_with_only_the_error(frames, "provider_unavailable")
    assert ("audio", _PASSING) not in frames
    assert ("audio", _RECEIVING) not in frames
    assert synthesized == [_OPENING, _PASSING]
    assert open_attempt
    assert leases == 0


def test_the_synthesis_failing_on_the_second_line_keeps_the_first_line_heard(
    django_user_model, monkeypatch
):
    frames, leases, open_attempt, _ = _fail_in_the_round(
        monkeypatch,
        django_user_model,
        [_OPENING, _PASSING, _RECEIVING],
        synthesize=_failing_on(_RECEIVING),
    )

    assert frames[:3] == [speaker("Rachel"), ("audio", _PASSING), speaker("Tom")]
    assert len(frames) == 4
    _ends_with_only_the_error(frames, "provider_unavailable")
    assert open_attempt
    assert leases == 0
