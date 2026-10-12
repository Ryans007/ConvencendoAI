import json

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from django.test import override_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

STUDENT_SPEECH = "my card number is 4111 1111 1111 1111"
PERSONA_OPENING = "Hello, let's talk about the deadline."
PERSONA_REPLY = "Understood, let's proceed then."


def _run_session(django_user_model, monkeypatch) -> None:
    """Roda uma sessão completa de um turno, com os modelos e o áudio substituídos."""
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)

    turns = iter(
        [
            PersonaTurn(line=PERSONA_OPENING, pass_to="student", scene_resolved=False),
            PersonaTurn(line=PERSONA_REPLY, pass_to="student", scene_resolved=True),
        ]
    )

    class _FakePersonaLLM:
        def invoke(self, messages):
            return next(turns)

    class _FakeRoutingLLM:
        def invoke(self, messages):
            return RoutingDecision(speaker="")

    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _FakePersonaLLM()
    )
    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _FakeRoutingLLM()
    )
    monkeypatch.setattr(voice_consumers, "transcribe", lambda audio: STUDENT_SPEECH)
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")
    outcome = EvaluationOutcome(
        confirmed_criteria={"c1", "c2", "c3", "c4"},
        judged_dimensions=[
            JudgedDimension(dimension="fluency", value=15, weight=15),
            JudgedDimension(dimension="vocabulary", value=10, weight=10),
            JudgedDimension(dimension="grammar", value=15, weight=15),
            JudgedDimension(dimension="pragmatics", value=15, weight=15),
            JudgedDimension(dimension="autonomy", value=5, weight=5),
        ],
        feedback="Great job.",
        memory_summary="Negotiated a one-week extension.",
        review_items=[],
    )
    monkeypatch.setattr(
        "apps.agents.services.session_runner.evaluate",
        lambda content, messages, known_rules=(): outcome,
    )

    async def run() -> None:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/voice/{scenario.slug}/{level.order}/?token={token}",
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()
        await communicator.send_to(bytes_data=b"raw-student-audio")
        await communicator.receive_from()
        await communicator.receive_from()
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        await communicator.disconnect()

    async_to_sync(run)()


def test_a_production_session_leaves_no_speech_in_the_log(
    django_user_model, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Com o log de conversa desligado, nem a fala do aluno nem a das personas saem no log."""
    with override_settings(LOG_CONVERSATION_CONTENT=False):
        _run_session(django_user_model, monkeypatch)

    output = capsys.readouterr().out
    assert STUDENT_SPEECH not in output
    assert PERSONA_OPENING not in output
    assert PERSONA_REPLY not in output
    assert f"You: ({len(STUDENT_SPEECH)} caracteres)" in output


def test_a_development_session_logs_the_speech(
    django_user_model, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No desenvolvimento, as falas continuam aparecendo no log como sempre."""
    with override_settings(LOG_CONVERSATION_CONTENT=True):
        _run_session(django_user_model, monkeypatch)

    output = capsys.readouterr().out
    assert f"You: {STUDENT_SPEECH}" in output
    assert PERSONA_OPENING in output
