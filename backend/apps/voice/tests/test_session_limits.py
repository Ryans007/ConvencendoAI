import json
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.usage.models import AccessLimits, LiveSessionLease
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

_URL = "/ws/voice/negociar-prazo/3/?token={token}"


def _token(user) -> str:
    return str(AccessToken.for_user(user))


def _lease(user, minutes: int = 30) -> LiveSessionLease:
    return LiveSessionLease.objects.create(
        user=user, expires_at=timezone.now() + timedelta(minutes=minutes)
    )


def _attempts_today(user, count: int) -> None:
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    for _ in range(count):
        Attempt.objects.create(user=user, scenario=scenario, level=level)


def _refusal(token: str) -> tuple[dict, int]:
    """O aviso de erro da conexão recusada e quantas tentativas existem depois dela."""

    async def run() -> tuple[dict, int]:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), _URL.format(token=token)
        )
        connected, _ = await communicator.connect()
        assert connected
        payload = json.loads(await communicator.receive_from())
        attempts = await sync_to_async(Attempt.objects.count)()
        await communicator.disconnect()
        return payload, attempts

    return async_to_sync(run)()


def _fake_session(monkeypatch) -> None:
    class _Persona:
        def invoke(self, messages):
            return PersonaTurn(line="Hello there.", pass_to="student")

    class _Router:
        def invoke(self, messages):
            return RoutingDecision(speaker="")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda p, s: _Persona())
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda p, s: _Router())
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"wav")


def test_a_second_session_is_refused_with_its_own_code_and_opens_no_attempt(django_user_model):
    user = django_user_model.objects.create(username="maria")
    _lease(user)

    payload, attempts = _refusal(_token(user))

    assert payload["type"] == "error"
    assert payload["code"] == "session_already_open"
    assert attempts == 0


def test_the_daily_ceiling_refuses_the_next_session(django_user_model):
    user = django_user_model.objects.create(username="maria")
    _attempts_today(user, 20)

    payload, attempts = _refusal(_token(user))

    assert payload["code"] == "daily_session_limit"
    assert attempts == 20


def test_a_session_whose_lease_expired_does_not_block_a_new_one(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    LiveSessionLease.objects.create(user=user, expires_at=timezone.now() - timedelta(minutes=1))

    async def run() -> bytes:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), _URL.format(token=_token(user))
        )
        connected, _ = await communicator.connect()
        assert connected
        opening = await communicator.receive_from()
        await communicator.disconnect()
        return opening

    assert async_to_sync(run)() == b"wav"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_leaving_the_session_frees_the_next_one(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)

    async def run() -> tuple[int, int]:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), _URL.format(token=_token(user))
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()
        open_during = await sync_to_async(LiveSessionLease.objects.count)()
        await communicator.disconnect()
        open_after = await sync_to_async(LiveSessionLease.objects.count)()
        return open_during, open_after

    assert async_to_sync(run)() == (1, 0)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_refused_session_does_not_free_the_one_that_is_open(django_user_model):
    user = django_user_model.objects.create(username="maria")
    lease = _lease(user)

    _refusal(_token(user))

    assert LiveSessionLease.objects.filter(pk=lease.pk).exists()


def test_a_turn_audio_over_the_limit_is_refused_without_transcribing_or_ending(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    limits = AccessLimits.get_solo()
    limits.max_turn_audio_kb = 1
    limits.save()

    def must_not_transcribe(audio):
        raise AssertionError("o áudio grande não pode ser transcrito")

    monkeypatch.setattr(voice_consumers, "transcribe", must_not_transcribe)

    async def run() -> dict:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), _URL.format(token=_token(user))
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()
        await communicator.send_to(bytes_data=b"x" * 2048)
        payload = json.loads(await communicator.receive_from())
        assert await communicator.receive_nothing()
        await communicator.disconnect()
        return payload

    assert async_to_sync(run)() == {"type": "audio_too_large"}


def test_a_turn_audio_within_the_limit_is_transcribed_as_before(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    monkeypatch.setattr(voice_consumers, "transcribe", lambda audio: "   ")

    async def run() -> dict:
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), _URL.format(token=_token(user))
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_from()
        await communicator.send_to(bytes_data=b"x" * 512)
        payload = json.loads(await communicator.receive_from())
        await communicator.disconnect()
        return payload

    assert async_to_sync(run)() == {"type": "no_speech"}
