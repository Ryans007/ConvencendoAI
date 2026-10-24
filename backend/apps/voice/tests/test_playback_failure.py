import json

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.services.stt import Transcription
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

_OPENING = PersonaTurn(line="Hello, let's talk.", pass_to="student")
_REPLY = PersonaTurn(line="Understood, go on.", pass_to="student")


class _ScriptedPersonaLLM:
    def __init__(self, *turns: PersonaTurn):
        self._turns = iter(turns)

    def invoke(self, messages):
        return next(self._turns)


class _NobodyAddressed:
    def invoke(self, messages):
        return RoutingDecision(speaker="")


async def _keep_the_test_connection() -> None:
    """Impede o Channels de fechar a conexão do teste a cada mensagem de texto recebida."""


def _run_with_playback_report(django_user_model, monkeypatch, report: dict) -> None:
    """Abre uma sessão, manda o aviso de recusa de reprodução e confere que ela segue."""
    monkeypatch.setattr("channels.consumer.aclose_old_connections", _keep_the_test_connection)
    persona = _ScriptedPersonaLLM(_OPENING, _REPLY)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _NobodyAddressed()
    )
    monkeypatch.setattr(
        voice_consumers,
        "transcribe_with_words",
        lambda audio: Transcription("I need one more week."),
    )
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))

    async def run() -> None:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_persona_audio()

        await communicator.send_to(text_data=json.dumps(report))

        await communicator.send_to(bytes_data=b"raw-student-audio")
        await communicator.receive_persona_audio()
        await communicator.disconnect()

    async_to_sync(run)()


def test_a_refused_playback_is_logged_with_the_error_name(
    django_user_model, monkeypatch, capsys: pytest.CaptureFixture[str]
):
    _run_with_playback_report(
        django_user_model,
        monkeypatch,
        {"type": "playback_failed", "reason": "NotAllowedError"},
    )

    assert "[session] o navegador recusou tocar o audio: NotAllowedError" in capsys.readouterr().out


@pytest.mark.parametrize(
    "reason",
    ["Not Allowed", "x" * 41, "line one\nforged log line", "", 42, None, ["NotAllowedError"]],
)
def test_a_reason_outside_the_format_is_logged_as_unknown(
    django_user_model, monkeypatch, capsys: pytest.CaptureFixture[str], reason
):
    _run_with_playback_report(
        django_user_model, monkeypatch, {"type": "playback_failed", "reason": reason}
    )

    output = capsys.readouterr().out
    assert "[session] o navegador recusou tocar o audio: desconhecido" in output
    assert "forged log line" not in output
