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
from apps.progress.models import Attempt
from apps.usage.models import LiveSessionLease
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns

pytestmark = pytest.mark.django_db

_PATH = "/ws/voice/negociar-prazo/3/"


def _token(user) -> str:
    return str(AccessToken.for_user(user))


def _auth(token) -> str:
    return json.dumps({"type": "auth", "token": token})


def _fake_session(monkeypatch) -> None:
    class _Persona:
        def invoke(self, messages):
            return PersonaTurn(line="Hello there.", pass_to="student")

    class _Router:
        def invoke(self, messages):
            return RoutingDecision(speaker="")

    def must_not_transcribe(audio):
        raise AssertionError("nada pode ser transcrito antes da autenticação")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda p, s: _Persona())
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda p, s: _Router())
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"wav")
    monkeypatch.setattr(voice_consumers, "transcribe", must_not_transcribe)


def _run(path: str, send, *, wait: float = 1):
    """Abre a conexão pura, manda o que `send` disser e devolve a primeira resposta e o banco."""

    async def run():
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), path)
        connected, _ = await communicator.connect()
        assert connected
        await send(communicator)
        first = await communicator.receive_from(timeout=wait)
        state = {
            "attempts": await sync_to_async(Attempt.objects.count)(),
            "leases": await sync_to_async(LiveSessionLease.objects.count)(),
        }
        await communicator.disconnect()
        return (first if isinstance(first, bytes) else json.loads(first)), state

    return async_to_sync(run)()


def _sender(text=None, data=None):
    async def send(communicator):
        if text is not None:
            await communicator.send_to(text_data=text)
        if data is not None:
            await communicator.send_to(bytes_data=data)

    return send


def test_the_token_in_the_first_message_starts_the_session(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)

    first, state = _run(_PATH, _sender(_auth(_token(user))))

    assert first["type"] == "speaker"
    assert state["attempts"] == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_url_never_needs_the_token_to_carry_the_other_parameters(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)

    first, state = _run(f"{_PATH}?hints=1", _sender(_auth(_token(user))))

    assert first["type"] == "speaker"
    assert Attempt.objects.get().hints_enabled is True


def test_a_token_only_in_the_url_does_not_start_the_session(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    monkeypatch.setattr(voice_consumers, "_AUTH_TIMEOUT_SECONDS", 0.2)

    first, state = _run(f"{_PATH}?token={_token(user)}", _sender(), wait=3)

    assert first["type"] == "error"
    assert state == {"attempts": 0, "leases": 0}


@pytest.mark.parametrize(
    "message",
    [
        json.dumps({"type": "auth"}),
        json.dumps({"type": "auth", "token": ""}),
        json.dumps({"type": "auth", "token": 12345}),
        json.dumps({"type": "hello", "token": "x"}),
        json.dumps(["auth"]),
        "isto não é json",
    ],
)
def test_a_first_message_that_is_not_a_valid_authentication_ends_the_connection(
    django_user_model, monkeypatch, message
):
    _fake_session(monkeypatch)

    first, state = _run(_PATH, _sender(message))

    assert first["type"] == "error"
    assert state == {"attempts": 0, "leases": 0}


def test_an_invalid_token_is_refused(monkeypatch):
    _fake_session(monkeypatch)

    first, state = _run(_PATH, _sender(_auth("not-a-real-token")))

    assert first["type"] == "error"
    assert state == {"attempts": 0, "leases": 0}


def test_an_expired_token_is_refused(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    token = AccessToken.for_user(user)
    token.set_exp(from_time=timezone.now() - timedelta(hours=1), lifetime=timedelta(minutes=1))

    first, state = _run(_PATH, _sender(_auth(str(token))))

    assert first["type"] == "error"
    assert state == {"attempts": 0, "leases": 0}


def test_audio_before_the_authentication_ends_the_connection_without_transcribing(
    django_user_model, monkeypatch
):
    _fake_session(monkeypatch)

    first, state = _run(_PATH, _sender(data=b"raw-student-audio"))

    assert first["type"] == "error"
    assert state == {"attempts": 0, "leases": 0}


def test_an_authentication_message_that_is_too_large_is_not_read_as_a_token(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    huge = json.dumps({"type": "auth", "token": _token(user) + "x" * 5000})

    first, state = _run(_PATH, _sender(huge))

    assert first["type"] == "error"
    assert "grande demais" in first["message"]
    assert state == {"attempts": 0, "leases": 0}


def test_silence_after_opening_ends_the_connection_without_reserving_anything(monkeypatch):
    _fake_session(monkeypatch)
    monkeypatch.setattr(voice_consumers, "_AUTH_TIMEOUT_SECONDS", 0.2)

    first, state = _run(_PATH, _sender(), wait=3)

    assert first["type"] == "error"
    assert "a tempo" in first["message"]
    assert state == {"attempts": 0, "leases": 0}


def test_the_deadline_does_not_cut_a_session_that_authenticated_in_time(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)
    monkeypatch.setattr(voice_consumers, "_AUTH_TIMEOUT_SECONDS", 0.2)

    async def run():
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), _PATH)
        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_to(text_data=_auth(_token(user)))
        assert json.loads(await communicator.receive_from())["type"] == "speaker"
        opening = await communicator.receive_from()
        assert await communicator.receive_nothing(timeout=0.6)
        await communicator.disconnect()
        return opening

    assert async_to_sync(run)() == b"wav"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_second_authentication_message_is_ignored_and_the_session_goes_on(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="maria")
    _fake_session(monkeypatch)

    async def run():
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), _PATH)
        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_to(text_data=_auth(_token(user)))
        assert json.loads(await communicator.receive_from())["type"] == "speaker"
        opening = await communicator.receive_from()
        await communicator.send_to(text_data=_auth(_token(user)))
        quiet = await communicator.receive_nothing(timeout=0.3)
        attempts = await sync_to_async(Attempt.objects.count)()
        await communicator.disconnect()
        return opening, quiet, attempts

    assert async_to_sync(run)() == (b"wav", True, 1)
