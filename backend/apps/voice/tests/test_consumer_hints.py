import json

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.progress.models import Attempt
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

_HINT_REQUEST = json.dumps({"type": "hint_request"})
_SUGGESTION = "Preciso de mais uma semana, porque o escopo aumentou."


class _ScriptedPersonaLLM:
    def __init__(self, *turns: PersonaTurn):
        self._turns = iter(turns)

    def invoke(self, messages):
        return next(self._turns)


class _NobodyAddressed:
    def invoke(self, messages):
        return RoutingDecision(speaker="")


class _AlwaysRachel:
    def invoke(self, messages):
        return RoutingDecision(speaker="rachel")


def _turn(line: str, resolved: bool = False) -> PersonaTurn:
    return PersonaTurn(line=line, pass_to="student", scene_resolved=resolved)


async def _keep_the_test_connection() -> None:
    """Substitui o fechamento de conexões que o Channels faz a cada mensagem recebida.

    O teste roda dentro de uma transação que o pytest-django desfaz no fim, e o Channels
    fecha a conexão por ela não estar em autocommit: depois da primeira mensagem de texto,
    toda consulta do teste falharia com "the connection is closed". Fora dos testes, o
    fechamento continua acontecendo normalmente.
    """


def _prepare(monkeypatch, *turns, tutor=None, router=_NobodyAddressed):
    monkeypatch.setattr("channels.consumer.aclose_old_connections", _keep_the_test_connection)
    persona = _ScriptedPersonaLLM(*turns)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: router())
    monkeypatch.setattr(voice_consumers, "transcribe", lambda audio: "I need one more week.")
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")
    calls = []

    def fake_suggest(content, history):
        calls.append([m.content for m in history])
        if tutor is not None:
            return tutor()
        return _SUGGESTION

    monkeypatch.setattr(voice_consumers, "suggest_answer", fake_suggest)
    return calls


def _capture_evaluation(monkeypatch) -> list:
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


async def _connect(token, hints: bool):
    query = f"token={token}" + ("&hints=1" if hints else "")
    communicator = SessionCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?{query}"
    )
    connected, _ = await communicator.connect()
    assert connected
    assert await communicator.receive_from() == b"fake-wav-bytes"
    return communicator


def _attempt(user) -> Attempt:
    return Attempt.objects.get(user=user)


def test_hint_is_answered_counted_once_per_turn_and_marks_the_answer(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    calls = _prepare(
        monkeypatch,
        _turn("Why do you need more time?"),
        _turn("And what is your plan?"),
        _turn("Fine, take the week.", resolved=True),
        router=_AlwaysRachel,
    )
    evaluated = _capture_evaluation(monkeypatch)

    async def run() -> None:
        communicator = await _connect(token, hints=True)

        await communicator.send_to(text_data=_HINT_REQUEST)
        assert json.loads(await communicator.receive_from()) == {
            "type": "hint",
            "text": _SUGGESTION,
        }
        await communicator.send_to(text_data=_HINT_REQUEST)
        assert json.loads(await communicator.receive_from())["text"] == _SUGGESTION

        await communicator.send_to(bytes_data=b"answer-after-hint")
        assert await communicator.receive_from() == b"fake-wav-bytes"
        await communicator.send_to(bytes_data=b"answer-without-hint")
        assert await communicator.receive_from() == b"fake-wav-bytes"
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        assert json.loads(await communicator.receive_from())["type"] == "session_ended"
        attempt = await sync_to_async(_attempt)(user)
        assert attempt.hints_enabled is True
        assert attempt.hints_used == 1
        await communicator.disconnect()

    async_to_sync(run)()

    assert len(calls) == 1
    assert calls[0][-1].endswith("Why do you need more time?")
    student_turns = [m for m in evaluated[0] if m.type == "human"]
    assert student_turns[0].additional_kwargs == {"after_hint": True}
    assert student_turns[1].additional_kwargs == {}


def test_hint_request_is_ignored_when_the_session_started_without_hints(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    calls = _prepare(monkeypatch, _turn("Why do you need more time?"))

    async def run() -> None:
        communicator = await _connect(token, hints=False)

        await communicator.send_to(text_data=_HINT_REQUEST)
        assert await communicator.receive_nothing(timeout=0.5)
        attempt = await sync_to_async(_attempt)(user)
        assert attempt.hints_enabled is False
        assert attempt.hints_used == 0
        await communicator.disconnect()

    async_to_sync(run)()

    assert calls == []


@pytest.mark.parametrize(
    "tutor",
    [lambda: "", lambda: (_ for _ in ()).throw(RuntimeError("provedor fora"))],
    ids=["sugestao_vazia", "falha_do_tutor"],
)
def test_hint_that_cannot_be_generated_is_reported_and_the_session_goes_on(
    django_user_model, monkeypatch, tutor
):
    user, token = _student(django_user_model)
    _prepare(
        monkeypatch,
        _turn("Why do you need more time?"),
        _turn("And what is your plan?"),
        tutor=tutor,
    )

    async def run() -> None:
        communicator = await _connect(token, hints=True)

        await communicator.send_to(text_data=_HINT_REQUEST)
        assert json.loads(await communicator.receive_from()) == {"type": "hint_unavailable"}

        await communicator.send_to(bytes_data=b"student-turn")
        assert await communicator.receive_from() == b"fake-wav-bytes"
        assert (await sync_to_async(_attempt)(user)).hints_used == 0
        await communicator.disconnect()

    async_to_sync(run)()


def test_unknown_client_messages_are_ignored(django_user_model, monkeypatch):
    _, token = _student(django_user_model)
    calls = _prepare(monkeypatch, _turn("Why do you need more time?"))

    async def run() -> None:
        communicator = await _connect(token, hints=True)

        await communicator.send_to(text_data="not json")
        await communicator.send_to(text_data=json.dumps({"type": "something_else"}))
        assert await communicator.receive_nothing(timeout=0.5)
        await communicator.disconnect()

    async_to_sync(run)()

    assert calls == []
