import json

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.scene_end import end_after_the_first_turn
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db


def test_live_session_opens_transcribes_a_turn_and_ends(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)

    opening_turn = PersonaTurn(
        line="Hello, let's talk about the deadline.", pass_to="student"
    )
    reply_turn = PersonaTurn(
        line="Understood, let's proceed then.", pass_to="student"
    )
    turns = iter([opening_turn, reply_turn])
    end_after_the_first_turn(monkeypatch, "Understood, let's proceed then.")

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
        "apps.agents.services.session_runner.evaluate", lambda content, messages, known_rules=(): fake_outcome
    )

    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = SessionCommunicator(
            application, f"/ws/voice/{scenario.slug}/{level.order}/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected

        opening_audio = await communicator.receive_from()
        assert opening_audio == b"fake-wav-bytes"

        await communicator.send_to(bytes_data=b"raw-student-audio")

        reply_audio = await communicator.receive_from()
        assert reply_audio == b"fake-wav-bytes"

        evaluating = json.loads(await communicator.receive_from())
        assert evaluating == {"type": "evaluating"}

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


def test_audio_sent_during_evaluation_is_ignored(django_user_model, monkeypatch):
    """Um áudio que chega enquanto a cena termina fica na fila do consumer; quando é
    processado, a cena já acabou, e ele não pode transcrever, avaliar nem gravar de novo."""
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))

    turns = iter([
        PersonaTurn(line="Hello, let's talk.", pass_to="student"),
        PersonaTurn(line="Deal, see you next week.", pass_to="student"),
    ])

    class _FakeStructuredLLM:
        def invoke(self, messages):
            return next(turns)

    class _FakeRoutingLLM:
        def invoke(self, messages):
            return RoutingDecision(speaker="")

    end_after_the_first_turn(monkeypatch)
    transcribed, evaluated = [], []
    outcome = EvaluationOutcome(
        confirmed_criteria=set(),
        judged_dimensions=[JudgedDimension(dimension="fluency", value=10, weight=15)],
        feedback="Ok.",
        memory_summary="Pediu mais prazo.",
        review_items=[],
    )

    def fake_evaluate(content, messages, known_rules=()):
        evaluated.append(messages)
        return outcome

    def fake_transcribe(audio):
        transcribed.append(audio)
        return "I need one more week."

    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _FakeStructuredLLM()
    )
    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _FakeRoutingLLM()
    )
    monkeypatch.setattr(voice_consumers, "transcribe", fake_transcribe)
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")
    monkeypatch.setattr("apps.agents.services.session_runner.evaluate", fake_evaluate)

    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = SessionCommunicator(
            application, f"/ws/voice/negociar-prazo/3/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected
        assert await communicator.receive_from() == b"fake-wav-bytes"

        await communicator.send_to(bytes_data=b"last-student-turn")
        await communicator.send_to(bytes_data=b"spoken-during-evaluation")

        assert await communicator.receive_from() == b"fake-wav-bytes"
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        assert (await communicator.receive_output())["type"] == "websocket.close"
        assert await communicator.receive_nothing(timeout=0.5)

        assert transcribed == [b"last-student-turn"]
        assert len(evaluated) == 1

        await communicator.disconnect()

    async_to_sync(run)()


def test_empty_transcription_asks_the_student_to_speak_again(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))

    opening_turn = PersonaTurn(line="Hello, let's talk.", pass_to="student")

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
        communicator = SessionCommunicator(
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
        communicator = SessionCommunicator(application, "/ws/voice/negociar-prazo/3/")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_to(text_data=json.dumps({"type": "auth"}))

        control = await communicator.receive_from()
        payload = json.loads(control)
        assert payload["type"] == "error"

        await communicator.disconnect()

    async_to_sync(run)()


def test_live_session_fails_explicitly_for_invalid_token():
    async def run() -> None:
        application = URLRouter(websocket_urlpatterns)
        communicator = SessionCommunicator(
            application, "/ws/voice/negociar-prazo/3/?token=not-a-real-token"
        )
        connected, _ = await communicator.connect()
        assert connected

        control = await communicator.receive_from()
        payload = json.loads(control)
        assert payload["type"] == "error"

        await communicator.disconnect()

    async_to_sync(run)()


def _connection_error(token: str) -> tuple[dict, int]:
    """O aviso de erro da conexão e quantas tentativas existem depois dela."""

    async def run() -> tuple[dict, int]:
        application = URLRouter(websocket_urlpatterns)
        communicator = SessionCommunicator(
            application, f"/ws/voice/negociar-prazo/3/?token={token}"
        )
        connected, _ = await communicator.connect()
        assert connected

        payload = json.loads(await communicator.receive_from())
        attempts = await sync_to_async(Attempt.objects.count)()
        await communicator.disconnect()
        return payload, attempts

    return async_to_sync(run)()


def test_live_session_refuses_a_user_deactivated_after_the_token_was_issued(django_user_model):
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))
    user.is_active = False
    user.save(update_fields=["is_active"])

    payload, attempts = _connection_error(token)

    assert payload["type"] == "error"
    assert attempts == 0


def test_live_session_refuses_a_token_of_a_user_that_no_longer_exists(django_user_model):
    user = django_user_model.objects.create(username="aluno")
    token = str(AccessToken.for_user(user))
    user.delete()

    payload, attempts = _connection_error(token)

    assert payload["type"] == "error"
    assert attempts == 0


def test_live_session_refuses_a_user_that_still_has_to_change_the_password(django_user_model):
    user = django_user_model.objects.create(username="aluno", must_change_password=True)
    token = str(AccessToken.for_user(user))

    payload, attempts = _connection_error(token)

    assert payload["type"] == "error"
    assert "senha" in payload["message"]
    assert attempts == 0
