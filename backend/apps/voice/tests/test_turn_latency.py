import asyncio
import json

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.voice.routing import websocket_urlpatterns
from apps.voice.services.turn_latency import (
    TurnMarks,
    format_turn_latency,
    valid_count,
    valid_latency_ms,
)
from apps.voice.tests.round_shapes import connect, install, read_frames, student_token
from apps.voice.tests.session_client import SessionCommunicator
from apps.voice.tests.test_consumer_speech_turns import _prepare, _ScriptedPersonaLLM, _token

pytestmark = pytest.mark.django_db


async def _let_the_opening_settle() -> None:
    """Dá à sessão o instante de se declarar pronta antes de o teste responder.

    O servidor guarda a resposta que chega antes disso, e cancelar uma conexão que fecha logo em
    seguida descarta o que ainda não foi atendido. Um aluno de verdade só responde depois de ouvir
    a abertura, o que leva segundos; o teste, que responde na hora, espera.
    """
    await asyncio.sleep(0.1)


def _report(token: str, *reports: dict, audios: int = 1) -> None:
    """Abre a sessão, manda os áudios e depois os relatos de latência do navegador."""

    async def run() -> None:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_persona_audio()
        await _let_the_opening_settle()
        for _ in range(audios):
            await communicator.send_to(bytes_data=b"student-audio")
            await communicator.receive_persona_audio()
        for report in reports:
            await communicator.send_to(text_data=json.dumps(report))
        await communicator.disconnect()

    async_to_sync(run)()


def _latency_lines(capsys) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith("[latency]")]


def test_the_line_has_the_total_and_the_stage_breakdown():
    marks = TurnMarks(
        audio_received_at=0.0,
        stt_ms=700,
        graph_ms=1800,
        graph_total_ms=2700,
        tts_ms=900,
        server_ms=3500,
        lines=2,
    )

    line = format_turn_latency(7, 2, marks, 4200)

    assert line == (
        "[latency] attempt=7 turn=2 lines=2 total_ms=4200 server_ms=3500 stt_ms=700 "
        "graph_ms=1800 graph_total_ms=2700 tts_ms=900 outside_server_ms=700 "
        "underruns=n/a cut_lines=n/a"
    )


def test_an_unfinished_stage_shows_as_not_available():
    marks = TurnMarks(audio_received_at=0.0, stt_ms=700)

    line = format_turn_latency(7, 1, marks, 4200)

    assert "server_ms=n/a" in line
    assert "outside_server_ms=n/a" in line
    assert "lines=n/a" in line


@pytest.mark.parametrize("raw", [-1, 11 * 60 * 1000, "4200", True, None, [4200]])
def test_an_invalid_latency_is_discarded(raw):
    assert valid_latency_ms(raw) is None


def test_a_valid_latency_is_rounded_to_whole_milliseconds():
    assert valid_latency_ms(4200.6) == 4201


def test_the_browser_report_writes_one_line_with_the_server_stages(
    django_user_model, monkeypatch, capsys
):
    _prepare(monkeypatch)

    _report(_token(django_user_model), {"type": "turn_latency", "total_ms": 4200})

    [line] = _latency_lines(capsys)
    assert "turn=1" in line
    assert "lines=1" in line
    assert "total_ms=4200" in line
    for stage in ("server_ms", "stt_ms", "graph_ms", "tts_ms", "outside_server_ms"):
        assert f"{stage}=n/a" not in line


def test_a_second_report_for_the_same_turn_writes_nothing(django_user_model, monkeypatch, capsys):
    _prepare(monkeypatch)

    _report(
        _token(django_user_model),
        {"type": "turn_latency", "total_ms": 4200},
        {"type": "turn_latency", "total_ms": 4300},
    )

    assert len(_latency_lines(capsys)) == 1


def test_a_report_before_any_student_audio_writes_nothing(django_user_model, monkeypatch, capsys):
    _prepare(monkeypatch)

    _report(_token(django_user_model), {"type": "turn_latency", "total_ms": 4200}, audios=0)

    assert _latency_lines(capsys) == []


@pytest.mark.parametrize("total_ms", [-5, 11 * 60 * 1000, "4200", True, None])
def test_an_invalid_report_writes_nothing(django_user_model, monkeypatch, capsys, total_ms):
    _prepare(monkeypatch)

    _report(_token(django_user_model), {"type": "turn_latency", "total_ms": total_ms})

    assert _latency_lines(capsys) == []


def test_each_turn_is_numbered_in_its_own_line(django_user_model, monkeypatch, capsys):
    _prepare(monkeypatch)
    persona = _ScriptedPersonaLLM(
        *(PersonaTurn(line=f"Line {number}?", pass_to="student") for number in range(3))
    )
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(graph_routing, "should_hand_over", lambda *args, **kwargs: False)
    token = _token(django_user_model)

    async def run() -> None:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?token={token}"
        )
        await communicator.connect()
        await communicator.receive_persona_audio()
        await _let_the_opening_settle()
        for total in (3000, 3500):
            await communicator.send_to(bytes_data=b"student-audio")
            await communicator.receive_persona_audio()
            await communicator.send_to(
                text_data=json.dumps({"type": "turn_latency", "total_ms": total})
            )
        await communicator.disconnect()

    async_to_sync(run)()

    first, second = _latency_lines(capsys)
    assert "turn=1" in first and "total_ms=3000" in first
    assert "turn=2" in second and "total_ms=3500" in second


def test_the_line_carries_the_underruns_and_cut_lines_the_browser_counted():
    marks = TurnMarks(audio_received_at=0.0, stt_ms=700, graph_ms=1800, tts_ms=900, server_ms=3500)

    line = format_turn_latency(7, 2, marks, 4200, underruns=2, cut_lines=1)

    assert line.endswith("outside_server_ms=700 underruns=2 cut_lines=1")


def test_a_browser_that_does_not_count_shows_the_counts_as_not_available():
    marks = TurnMarks(audio_received_at=0.0, stt_ms=700, graph_ms=1800, tts_ms=900, server_ms=3500)

    line = format_turn_latency(7, 2, marks, 4200)

    assert line.endswith("underruns=n/a cut_lines=n/a")


@pytest.mark.parametrize("raw", [-1, 1001, "2", True, None, 2.5, [2]])
def test_an_invalid_count_is_discarded(raw):
    assert valid_count(raw) is None


def test_a_valid_count_is_kept_and_the_maximum_can_be_set():
    assert valid_count(0) == 0
    assert valid_count(37) == 37
    assert valid_count(5_000_000, maximum=20_000_000) == 5_000_000
    assert valid_count(20_000_001, maximum=20_000_000) is None


def test_the_report_with_the_counts_writes_them_in_the_same_line(
    django_user_model, monkeypatch, capsys
):
    _prepare(monkeypatch)

    _report(
        _token(django_user_model),
        {"type": "turn_latency", "total_ms": 4200, "underruns": 2, "cut_lines": 1},
    )

    [line] = _latency_lines(capsys)
    assert "underruns=2" in line
    assert "cut_lines=1" in line


def test_an_invalid_count_does_not_discard_the_latency_of_the_turn(
    django_user_model, monkeypatch, capsys
):
    _prepare(monkeypatch)

    _report(
        _token(django_user_model),
        {"type": "turn_latency", "total_ms": 4200, "underruns": -3, "cut_lines": "x"},
    )

    [line] = _latency_lines(capsys)
    assert "total_ms=4200" in line
    assert "underruns=n/a" in line
    assert "cut_lines=n/a" in line


def test_a_round_with_two_lines_reports_lines_two(django_user_model, monkeypatch, capsys):
    install(
        monkeypatch,
        ["Hello, let's talk.", "That one is for Tom.", "Sure. What is still missing?"],
        RoutingDecision(speaker="rachel", topic_owner="tom"),
    )
    token = student_token(django_user_model)

    async def run() -> None:
        communicator = await connect(token)
        await read_frames(communicator, 1)
        await _let_the_opening_settle()
        await communicator.send_to(bytes_data=b"student-audio")
        await read_frames(communicator, 2)
        await communicator.send_to(text_data=json.dumps({"type": "turn_latency", "total_ms": 5000}))
        await communicator.disconnect()

    async_to_sync(run)()

    [line] = _latency_lines(capsys)
    assert "lines=2" in line
    assert "total_ms=5000" in line
