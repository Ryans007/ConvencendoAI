import json

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns

pytestmark = pytest.mark.django_db


def test_live_session_opens_transcribes_a_turn_and_ends(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)

    opening_turn = PersonaTurn(
        line="Hello, let's talk about the deadline.", pass_to="student", scene_resolved=False
    )
    reply_turn = PersonaTurn(
        line="Understood, let's proceed then.", pass_to="student", scene_resolved=True
    )
    turns = iter([opening_turn, reply_turn])

    class _FakeStructuredLLM:
        def invoke(self, messages):
            return next(turns)

    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _FakeStructuredLLM()
    )

    class _FakeRoutingLLM:
        def invoke(self, messages):
            return RoutingDecision(speaker="")

    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _FakeRoutingLLM()
    )
    monkeypatch.setattr(voice_consumers, "transcribe", lambda audio: "I need one more week.")
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")

    fake_outcome = EvaluationOutcome(
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
        "apps.agents.services.session_runner.evaluate", lambda content, messages: fake_outcome
    )

    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(
            application, f"/ws/voice/{scenario.slug}/{level.order}/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected

        opening_audio = await communicator.receive_from()
        assert opening_audio == b"fake-wav-bytes"

        await communicator.send_to(bytes_data=b"raw-student-audio")

        reply_audio = await communicator.receive_from()
        assert reply_audio == b"fake-wav-bytes"

        control = await communicator.receive_from()
        payload = json.loads(control)
        assert payload["type"] == "session_ended"
        assert payload["final_score"] == 100
        assert payload["passed"] is True

        attempt = await sync_to_async(Attempt.objects.get)()
        assert attempt.user_id == user.id
        assert attempt.completed_at is not None
        assert attempt.final_score == 100
        assert payload["attempt_id"] == attempt.pk

        await communicator.disconnect()

    async_to_sync(run)()


def test_empty_transcription_asks_the_student_to_speak_again(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))

    opening_turn = PersonaTurn(line="Hello, let's talk.", pass_to="student", scene_resolved=False)

    class _FakeStructuredLLM:
        def invoke(self, messages):
            return opening_turn

    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _FakeStructuredLLM()
    )
    monkeypatch.setattr(voice_consumers, "transcribe", lambda audio: "   ")
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")

    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(
            application, f"/ws/voice/negociar-prazo/3/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected
        assert await communicator.receive_from() == b"fake-wav-bytes"

        await communicator.send_to(bytes_data=b"silent-audio")

        payload = json.loads(await communicator.receive_from())
        assert payload == {"type": "no_speech"}
        assert await communicator.receive_nothing()

        attempt = await sync_to_async(Attempt.objects.get)()
        assert attempt.completed_at is None

        await communicator.disconnect()

    async_to_sync(run)()


def test_live_session_fails_explicitly_without_token():
    """A conexão é aceita e depois recusada com uma mensagem clara, em vez de ser
    derrubada sem explicação."""

    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/voice/negociar-prazo/3/")
        connected, _ = await communicator.connect()
        assert connected

        control = await communicator.receive_from()
        payload = json.loads(control)
        assert payload["type"] == "error"

        await communicator.disconnect()

    async_to_sync(run)()


def test_live_session_fails_explicitly_for_invalid_token():
    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(
            application, "/ws/voice/negociar-prazo/3/?token=not-a-real-token"
        )
        connected, _ = await communicator.connect()
        assert connected

        control = await communicator.receive_from()
        payload = json.loads(control)
        assert payload["type"] == "error"

        await communicator.disconnect()

    async_to_sync(run)()
