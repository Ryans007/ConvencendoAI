import json
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.usage.models import LiveSessionLease
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns

pytestmark = pytest.mark.django_db

_PASSWORD = "Xk9#mQ2vLp8Z"


def _url(slug: str, level: int, token: str) -> str:
    return f"/ws/voice/{slug}/{level}/?token={token}"


def _token(user) -> str:
    return str(AccessToken.for_user(user))


def _fake_models(monkeypatch) -> None:
    class _Persona:
        def invoke(self, messages):
            return PersonaTurn(line="Hello there.", pass_to="student", scene_resolved=False)

    class _Router:
        def invoke(self, messages):
            return RoutingDecision(speaker="")

    def must_not_call(*args, **kwargs):
        raise AssertionError("nenhum modelo pode ser chamado numa sessão recusada")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda p, s: _Persona())
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda p, s: _Router())
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"wav")
    monkeypatch.setattr(voice_consumers, "transcribe", must_not_call)


def _complete(user, slug: str, level: int, *, passed: bool, hours_ago: float) -> None:
    attempt = Attempt.objects.create(
        user=user, scenario=Scenario.objects.get(slug=slug), level=Level.objects.get(order=level)
    )
    attempt.final_score = 80 if passed else 40
    attempt.passed = passed
    attempt.completed_at = timezone.now() - timedelta(hours=hours_ago)
    attempt.save()


def _open(slug: str, level: int, token: str) -> tuple[dict | bytes, dict]:
    """A primeira mensagem da conexão e o estado do banco logo depois dela."""

    async def run() -> tuple[dict | bytes, dict]:
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns), _url(slug, level, token)
        )
        connected, _ = await communicator.connect()
        assert connected
        first = await communicator.receive_from()
        state = {
            "attempts": await sync_to_async(Attempt.objects.count)(),
            "leases": await sync_to_async(LiveSessionLease.objects.count)(),
        }
        await communicator.disconnect()
        return (first if isinstance(first, bytes) else json.loads(first)), state

    return async_to_sync(run)()


def test_a_locked_scenario_is_refused_without_attempt_reservation_or_model(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create_user(username="maria", password=_PASSWORD)
    _fake_models(monkeypatch)

    first, state = _open("problema-no-quarto", 3, _token(user))

    assert first["type"] == "error"
    assert first["code"] == "scenario_locked"
    assert "retry_after_seconds" not in first
    assert state == {"attempts": 0, "leases": 0}


def test_a_level_in_cooldown_is_refused_with_the_time_left(django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(username="maria", password=_PASSWORD)
    _fake_models(monkeypatch)
    hours = Scenario.objects.get(slug="entrevista-de-emprego").cooldown_hours
    _complete(user, "entrevista-de-emprego", 1, passed=False, hours_ago=2)

    first, state = _open("entrevista-de-emprego", 1, _token(user))

    assert first["code"] == "level_in_cooldown"
    assert abs(first["retry_after_seconds"] - (hours - 2) * 3600) <= 5
    assert state["leases"] == 0
    assert state["attempts"] == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_refusal_does_not_hold_the_session_the_next_one_needs(django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(username="maria", password=_PASSWORD)
    _fake_models(monkeypatch)
    token = _token(user)

    refused, _ = _open("problema-no-quarto", 3, token)
    allowed, state = _open("entrevista-de-emprego", 1, token)

    assert refused["code"] == "scenario_locked"
    assert allowed == b"wav"
    assert state["attempts"] == 1


def test_another_level_of_a_scenario_in_cooldown_opens(django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(username="maria", password=_PASSWORD)
    _fake_models(monkeypatch)
    _complete(user, "entrevista-de-emprego", 1, passed=False, hours_ago=2)

    first, _ = _open("entrevista-de-emprego", 2, _token(user))

    assert first == b"wav"


def test_the_superuser_opens_a_locked_scenario(django_user_model, monkeypatch):
    boss = django_user_model.objects.create_superuser(
        username="chefe", email="c@empresa.com", password=_PASSWORD
    )
    _fake_models(monkeypatch)

    first, state = _open("problema-no-quarto", 3, _token(boss))

    assert first == b"wav"
    assert state["attempts"] == 1


def test_a_scenario_that_does_not_exist_keeps_the_usual_answer(django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(username="maria", password=_PASSWORD)
    _fake_models(monkeypatch)

    first, _ = _open("nao-existe", 1, _token(user))

    assert first["type"] == "error"
    assert "code" not in first or first["code"] not in ("scenario_locked", "level_in_cooldown")
