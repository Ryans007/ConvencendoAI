import json

import pytest
from asgiref.sync import async_to_sync

from apps.agents.services.schemas import RoutingDecision
from apps.voice.tests.round_shapes import connect, install, student_token

pytestmark = pytest.mark.django_db

_NOBODY = RoutingDecision(speaker="none", topic_owner="none")


def _report_cut(django_user_model, monkeypatch, notice: dict, *, while_opening: bool = False) -> None:
    """Abre a sessão, manda o aviso de fala cortada e espera o servidor atendê-lo."""
    install(monkeypatch, ["Hello, let's talk."], _NOBODY)
    token = student_token(django_user_model)

    async def run() -> None:
        communicator = await connect(token)
        if while_opening:
            await communicator.send_to(text_data=json.dumps(notice))
        await communicator.receive_from()
        await communicator.receive_from()
        if not while_opening:
            await communicator.send_to(text_data=json.dumps(notice))
        await communicator.disconnect()

    async_to_sync(run)()


def _lines(capsys) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if "fala cortada" in line]


def test_a_cut_speech_is_written_to_the_server_log_with_the_two_counts(
    django_user_model, monkeypatch, capsys
):
    _report_cut(
        django_user_model,
        monkeypatch,
        {"type": "speech_cut", "expected_bytes": 341752, "received_bytes": 210000},
    )

    assert _lines(capsys) == [
        "[session] fala cortada no navegador: esperados 341752 bytes, recebidos 210000"
    ]


@pytest.mark.parametrize(
    "notice",
    [
        {"type": "speech_cut", "expected_bytes": -1, "received_bytes": 10},
        {"type": "speech_cut", "expected_bytes": "x", "received_bytes": 10},
        {"type": "speech_cut", "expected_bytes": 10**12, "received_bytes": 10},
        {"type": "speech_cut"},
    ],
)
def test_an_invalid_count_shows_as_unknown_and_never_breaks_the_session(
    django_user_model, monkeypatch, capsys, notice
):
    _report_cut(django_user_model, monkeypatch, notice)

    [line] = _lines(capsys)
    assert "desconhecido" in line


def test_the_notice_is_not_lost_while_the_session_still_opens(
    django_user_model, monkeypatch, capsys
):
    _report_cut(
        django_user_model,
        monkeypatch,
        {"type": "speech_cut", "expected_bytes": 100, "received_bytes": 40},
        while_opening=True,
    )

    assert _lines(capsys) == [
        "[session] fala cortada no navegador: esperados 100 bytes, recebidos 40"
    ]
