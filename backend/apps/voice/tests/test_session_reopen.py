import asyncio
import time

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.usage.models import LiveSessionLease
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

_URL = "/ws/voice/negociar-prazo/3/?token={token}"
_OPENING_SECONDS = 1.5


class _SlowFirstPersona:
    """Uma persona cuja primeira fala demora, como a abertura de uma sessão de verdade."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            time.sleep(_OPENING_SECONDS)
        return PersonaTurn(line="Hello there.", pass_to="student")


class _Router:
    def invoke(self, messages):
        return RoutingDecision(speaker="")


def _prepare(monkeypatch) -> None:
    persona = _SlowFirstPersona()
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda p, s: persona)
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda p, s: _Router())
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"wav")


def _communicator(user) -> SessionCommunicator:
    token = str(AccessToken.for_user(user))
    return SessionCommunicator(URLRouter(websocket_urlpatterns), _URL.format(token=token))


async def _wait_for_lease() -> None:
    """Espera a reserva da conexão existir, que é o sinal de que a abertura começou."""
    for _ in range(50):
        if await sync_to_async(LiveSessionLease.objects.exists)():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("a reserva da sessão nunca foi criada")


def test_a_connection_that_drops_while_opening_does_not_block_the_next(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _prepare(monkeypatch)

    async def run() -> bytes:
        discarded = _communicator(user)
        await discarded.connect()
        await _wait_for_lease()
        await discarded.disconnect()

        kept = _communicator(user)
        await kept.connect()
        _, opening = await kept.receive_persona_line()
        await kept.disconnect()
        return opening

    assert async_to_sync(run)() == b"wav"


def test_the_reservation_of_a_connection_that_dropped_while_opening_is_released(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _prepare(monkeypatch)

    async def run() -> int:
        discarded = _communicator(user)
        await discarded.connect()
        await _wait_for_lease()
        await discarded.disconnect()
        await asyncio.sleep(_OPENING_SECONDS + 0.5)
        return await sync_to_async(LiveSessionLease.objects.count)()

    assert async_to_sync(run)() == 0


def test_a_second_connection_is_still_refused_while_the_first_stays_open(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _prepare(monkeypatch)

    async def run() -> str:
        first = _communicator(user)
        await first.connect()
        await _wait_for_lease()

        second = _communicator(user)
        await second.connect()
        refusal = await second.receive_json_from()
        await second.disconnect()
        await first.disconnect()
        return refusal["code"]

    assert async_to_sync(run)() == "session_already_open"
