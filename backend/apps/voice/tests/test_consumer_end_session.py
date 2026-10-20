import json

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.progress.choices import EndedBy
from apps.progress.models import Attempt
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.scene_end import end_after_the_first_turn
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

_END_SESSION = json.dumps({"type": "end_session"})


class _ScriptedPersonaLLM:
    def __init__(self, *turns: PersonaTurn):
        self._turns = iter(turns)

    def invoke(self, messages):
        return next(self._turns)


class _NobodyAddressed:
    def invoke(self, messages):
        return RoutingDecision(speaker="")


async def _keep_the_test_connection() -> None:
    """Substitui o fechamento de conexões que o Channels faz a cada mensagem recebida.

    O teste roda dentro de uma transação que o pytest-django desfaz no fim, e o Channels fecha
    a conexão por ela não estar em autocommit: depois da primeira mensagem de texto, toda
    consulta do teste falharia com "the connection is closed".
    """


def _prepare(monkeypatch, *turns: PersonaTurn) -> list:
    monkeypatch.setattr("channels.consumer.aclose_old_connections", _keep_the_test_connection)
    persona = _ScriptedPersonaLLM(*turns)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _NobodyAddressed()
    )
    monkeypatch.setattr(voice_consumers, "transcribe", lambda audio: "I need one more week.")
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")
    evaluated = []

    def fake_evaluate(content, messages, known_rules=()):
        evaluated.append(list(messages))
        return EvaluationOutcome(
            confirmed_criteria=set(),
            judged_dimensions=[JudgedDimension(dimension="fluency", value=10, weight=15)],
            feedback="Ok.",
            memory_summary="Pediu mais prazo.",
            review_items=[],
        )

    monkeypatch.setattr("apps.agents.services.session_runner.evaluate", fake_evaluate)
    return evaluated


def _student(django_user_model):
    user = django_user_model.objects.create(username="aluno")
    return user, str(AccessToken.for_user(user))


async def _connect(token):
    communicator = SessionCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?token={token}"
    )
    connected, _ = await communicator.connect()
    assert connected
    assert await communicator.receive_from() == b"fake-wav-bytes"
    return communicator


def _attempt(user) -> Attempt:
    return Attempt.objects.get(user=user)


def test_the_student_ends_the_session_in_the_middle_and_gets_the_report(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    evaluated = _prepare(
        monkeypatch,
        PersonaTurn(line="Hello, let's talk about the deadline."),
        PersonaTurn(line="What have you finished so far?"),
    )

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.send_to(bytes_data=b"first-answer")
        assert await communicator.receive_from() == b"fake-wav-bytes"

        await communicator.send_to(text_data=_END_SESSION)

        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        ended = json.loads(await communicator.receive_from())
        assert ended["type"] == "session_ended"
        attempt = await sync_to_async(_attempt)(user)
        assert ended["attempt_id"] == attempt.pk
        assert attempt.completed_at is not None
        assert attempt.ended_by == EndedBy.STUDENT
        await communicator.disconnect()

    async_to_sync(run)()

    assert len(evaluated) == 1
    spoken = [message.content for message in evaluated[0]]
    assert spoken == [
        "[Rachel] Hello, let's talk about the deadline.",
        "I need one more week.",
        "[Rachel] What have you finished so far?",
    ]


def test_the_request_before_any_answer_is_ignored(django_user_model, monkeypatch):
    user, token = _student(django_user_model)
    evaluated = _prepare(monkeypatch, PersonaTurn(line="Hello, let's talk."))

    async def run() -> None:
        communicator = await _connect(token)

        await communicator.send_to(text_data=_END_SESSION)

        assert await communicator.receive_nothing(timeout=0.5)
        attempt = await sync_to_async(_attempt)(user)
        assert attempt.completed_at is None
        await communicator.disconnect()

    async_to_sync(run)()

    assert evaluated == []


def test_a_session_that_reaches_the_limit_records_the_turn_limit(django_user_model, monkeypatch):
    user, token = _student(django_user_model)
    _prepare(monkeypatch, PersonaTurn(line="Hello, let's talk."))
    end_after_the_first_turn(monkeypatch, "Deal, see you next week.")

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.send_to(bytes_data=b"only-answer")
        assert await communicator.receive_from() == b"fake-wav-bytes"
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        attempt = await sync_to_async(_attempt)(user)
        assert attempt.ended_by == EndedBy.TURN_LIMIT
        await communicator.disconnect()

    async_to_sync(run)()


def test_the_request_after_the_scene_ended_is_ignored(django_user_model, monkeypatch):
    user, token = _student(django_user_model)
    evaluated = _prepare(monkeypatch, PersonaTurn(line="Hello, let's talk."))
    end_after_the_first_turn(monkeypatch, "Deal, see you next week.")

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.send_to(bytes_data=b"only-answer")
        await communicator.send_to(text_data=_END_SESSION)

        assert await communicator.receive_from() == b"fake-wav-bytes"
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        assert (await communicator.receive_output())["type"] == "websocket.close"
        assert await communicator.receive_nothing(timeout=0.5)
        attempt = await sync_to_async(_attempt)(user)
        assert attempt.ended_by == EndedBy.TURN_LIMIT
        await communicator.disconnect()

    async_to_sync(run)()

    assert len(evaluated) == 1


def test_the_request_that_arrives_during_a_round_waits_for_the_round(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    evaluated = _prepare(
        monkeypatch,
        PersonaTurn(line="Hello, let's talk about the deadline."),
        PersonaTurn(line="What have you finished so far?"),
    )

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.send_to(bytes_data=b"first-answer")
        await communicator.send_to(text_data=_END_SESSION)

        assert await communicator.receive_from() == b"fake-wav-bytes"
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        attempt = await sync_to_async(_attempt)(user)
        assert attempt.ended_by == EndedBy.STUDENT
        await communicator.disconnect()

    async_to_sync(run)()

    assert len(evaluated) == 1
    assert [m.content for m in evaluated[0]][-1] == "[Rachel] What have you finished so far?"
