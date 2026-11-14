import asyncio
import json
import re
import threading
import time

import httpx
import openai
import pytest
from asgiref.sync import async_to_sync, sync_to_async

from apps.agents.graph import personas as graph_personas
from apps.agents.services.schemas import RoutingDecision
from apps.progress.models import Attempt
from apps.usage.models import LiveSessionLease
from apps.usage.services.owner import current_owner
from apps.voice.tests.round_shapes import connect, install, student_token
from apps.voice.tests.test_consumer_streaming import _read_line, _stream_with

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

_OPENING = "Hello, let's talk about the deadline."
_PASSING = "That one is for Tom."
_RECEIVING = "Sure. What is still missing on the export?"
_REDIRECT = RoutingDecision(speaker="rachel", topic_owner="tom")
_REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")
_STREAMING = pytest.mark.parametrize("stream_audio", [False, True], ids=["whole", "stream"])


class _Gate:
    """Trava a geração de uma fala até o teste liberá-la, para provar o que chega antes dela."""

    def __init__(self, text: str):
        self.text = text
        self.opened = threading.Event()
        self.reached = threading.Event()

    def __call__(self) -> str:
        self.reached.set()
        if not self.opened.wait(timeout=10):
            raise AssertionError("o teste nunca liberou a segunda fala")
        return self.text


async def _read_whole(communicator) -> tuple[dict, bytes]:
    speaker = json.loads(await communicator.receive_from())
    return speaker, await communicator.receive_from()


async def _read_any(communicator, stream_audio: bool) -> tuple[str, str]:
    """Lê uma fala do jeito que o navegador a recebe e devolve quem fala e o texto."""
    if stream_audio:
        line = await _read_line(communicator)
        return line["speaker"], b"".join(line["chunks"]).decode()
    speaker, audio = await _read_whole(communicator)
    return speaker["name"], audio.decode()


async def _wait_until(event: threading.Event) -> None:
    for _ in range(200):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("a segunda fala nunca começou a ser gerada")


@_STREAMING
def test_the_first_line_reaches_the_student_before_the_second_is_generated(
    django_user_model, monkeypatch, stream_audio
):
    gate = _Gate(_RECEIVING)
    install(monkeypatch, [_OPENING, _PASSING, gate], _REDIRECT)
    if stream_audio:
        _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> tuple[tuple, tuple]:
        try:
            communicator = await connect(token, stream_audio=stream_audio)
            await _read_any(communicator, stream_audio)
            await asyncio.sleep(0.1)
            await communicator.send_to(bytes_data=b"student-audio")
            first = await _read_any(communicator, stream_audio)
            assert not gate.opened.is_set()
            gate.opened.set()
            second = await _read_any(communicator, stream_audio)
            await communicator.disconnect()
            return first, second
        finally:
            gate.opened.set()

    first, second = async_to_sync(run)()

    assert first == ("Rachel", _PASSING)
    assert second == ("Tom", _RECEIVING)


@_STREAMING
def test_the_second_line_never_reaches_the_student_before_the_first_one_ends(
    django_user_model, monkeypatch, stream_audio
):
    def slow_first_synthesis(text, voice):
        if text == _PASSING:
            time.sleep(0.4)
        return text.encode()

    install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT, synthesize=slow_first_synthesis)
    if stream_audio:
        _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> list[tuple[str, str]]:
        communicator = await connect(token, stream_audio=stream_audio)
        await _read_any(communicator, stream_audio)
        await asyncio.sleep(0.1)
        await communicator.send_to(bytes_data=b"student-audio")
        lines = [await _read_any(communicator, stream_audio) for _ in range(2)]
        await communicator.disconnect()
        return lines

    assert async_to_sync(run)() == [("Rachel", _PASSING), ("Tom", _RECEIVING)]


@_STREAMING
def test_a_model_failure_on_the_second_line_after_the_first_was_sent_ends_the_session(
    django_user_model, monkeypatch, stream_audio
):
    released = threading.Event()

    def fail_once_the_student_heard_the_first_line() -> str:
        released.wait(timeout=10)
        raise openai.APIConnectionError(request=_REQUEST)

    install(monkeypatch, [_OPENING, _PASSING, fail_once_the_student_heard_the_first_line], _REDIRECT)
    if stream_audio:
        _stream_with(monkeypatch)
    token = student_token(django_user_model)

    async def run() -> tuple[tuple, list, int, bool]:
        communicator = await connect(token, stream_audio=stream_audio)
        await _read_any(communicator, stream_audio)
        await asyncio.sleep(0.1)
        await communicator.send_to(bytes_data=b"student-audio")
        first = await _read_any(communicator, stream_audio)
        released.set()
        rest = []
        while True:
            output = await communicator.receive_output()
            if output["type"] == "websocket.close":
                break
            rest.append(json.loads(output["text"]) if output.get("text") else ("audio",))
        await communicator.disconnect()
        leases = await sync_to_async(LiveSessionLease.objects.count)()
        open_attempt = await sync_to_async(lambda: Attempt.objects.get().completed_at is None)()
        return first, rest, leases, open_attempt

    first, rest, leases, open_attempt = async_to_sync(run)()

    assert first == ("Rachel", _PASSING)
    assert [frame["type"] for frame in rest] == ["error"]
    assert rest[0]["code"] == "provider_unavailable"
    assert open_attempt
    assert leases == 0


def test_a_line_announced_with_a_text_that_is_not_the_one_returned_ends_the_session(
    django_user_model, monkeypatch
):
    install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT)
    original = graph_personas._speak

    def lying_announcement(role, text):
        original(role, text)
        from langgraph.config import get_stream_writer

        get_stream_writer()({"speaker": role.name, "text": text + " (changed)"})

    monkeypatch.setattr(graph_personas, "_speak", lying_announcement)
    token = student_token(django_user_model)

    async def run() -> list:
        communicator = await connect(token)
        frames = []
        while True:
            output = await communicator.receive_output()
            if output["type"] == "websocket.close":
                break
            frames.append(json.loads(output["text"]) if output.get("text") else ("audio",))
        await communicator.disconnect()
        return frames

    frames = async_to_sync(run)()

    assert frames[-1]["type"] == "error"
    assert frames[-1]["code"] == "unexpected"


def test_the_models_and_the_synthesis_of_a_two_line_round_are_attributed_to_the_student(
    django_user_model, monkeypatch
):
    owners: dict[str, list] = {"model": [], "synthesis": []}

    def model_call() -> str:
        owners["model"].append(current_owner())
        return _RECEIVING

    def synthesis(text, voice):
        owners["synthesis"].append(current_owner())
        return text.encode()

    install(monkeypatch, [_OPENING, _PASSING, model_call], _REDIRECT, synthesize=synthesis)
    token = student_token(django_user_model)

    async def run() -> None:
        communicator = await connect(token)
        await _read_any(communicator, False)
        await asyncio.sleep(0.1)
        await communicator.send_to(bytes_data=b"student-audio")
        await _read_any(communicator, False)
        await _read_any(communicator, False)
        await communicator.disconnect()

    async_to_sync(run)()

    attempt = Attempt.objects.get()
    assert owners["model"] and all(o is not None and o.attempt_id == attempt.pk for o in owners["model"])
    assert len(owners["synthesis"]) == 3
    assert all(o is not None and o.attempt_id == attempt.pk for o in owners["synthesis"])


def _graph_times(capsys) -> tuple[int, int]:
    """O `graph_ms` e o `graph_total_ms` da única linha de latência que o servidor escreveu."""
    [line] = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("[latency]")
    ]
    first = int(re.search(r"graph_ms=(\d+)", line).group(1))
    total = int(re.search(r"graph_total_ms=(\d+)", line).group(1))
    return first, total


def _report_after_a_round(django_user_model, monkeypatch, lines, routing, *, reads: int) -> None:
    install(monkeypatch, lines, routing)
    token = student_token(django_user_model)

    async def run() -> None:
        communicator = await connect(token)
        await _read_any(communicator, False)
        await asyncio.sleep(0.1)
        await communicator.send_to(bytes_data=b"student-audio")
        for _ in range(reads):
            await _read_any(communicator, False)
        await communicator.send_to(text_data=json.dumps({"type": "turn_latency", "total_ms": 3000}))
        await communicator.disconnect()

    async_to_sync(run)()


def test_the_latency_line_shows_how_much_earlier_the_first_line_was_ready(
    django_user_model, monkeypatch, capsys
):
    def slow_second_line() -> str:
        time.sleep(0.6)
        return _RECEIVING

    _report_after_a_round(
        django_user_model, monkeypatch, [_OPENING, _PASSING, slow_second_line], _REDIRECT, reads=2
    )

    first_ready, all_ready = _graph_times(capsys)

    assert all_ready - first_ready >= 500


def test_in_a_round_of_one_line_the_two_graph_times_are_the_same(
    django_user_model, monkeypatch, capsys
):
    _report_after_a_round(
        django_user_model,
        monkeypatch,
        [_OPENING, "What have you finished so far?"],
        RoutingDecision(speaker="none", topic_owner="none"),
        reads=1,
    )

    first_ready, all_ready = _graph_times(capsys)

    assert 0 <= all_ready - first_ready <= 150
