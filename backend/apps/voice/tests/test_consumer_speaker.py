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

_LINES = [
    "Hello, let's talk about the deadline.",
    "That one is for Tom.",
    "Sure. What is still missing on the export?",
]


def _install(monkeypatch, routing: RoutingDecision) -> None:
    turns = iter(PersonaTurn(line=line, pass_to="student") for line in _LINES)

    class _Personas:
        def invoke(self, messages):
            return next(turns)

    class _Router:
        def invoke(self, messages):
            return routing

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _Personas())
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: _Router())
    monkeypatch.setattr(
        voice_consumers,
        "transcribe_with_words",
        lambda audio: Transcription("Rachel, I need more time."),
    )
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")


def _open(user) -> SessionCommunicator:
    token = str(AccessToken.for_user(user))
    return SessionCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?token={token}"
    )


def test_the_name_arrives_before_the_audio_and_never_carries_the_speech(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="aluno")
    _install(monkeypatch, RoutingDecision(speaker=""))

    async def run() -> tuple[str, str]:
        communicator = _open(user)
        connected, _ = await communicator.connect()
        assert connected
        announced = await communicator.receive_from()
        audio = await communicator.receive_from()
        await communicator.disconnect()
        return announced, audio

    announced, audio = async_to_sync(run)()

    assert json.loads(announced) == {"type": "speaker", "name": "Rachel"}
    assert "deadline" not in announced
    assert audio == b"fake-wav-bytes"


def test_two_lines_in_one_round_announce_each_speaker_before_its_audio(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="aluno")
    _install(monkeypatch, RoutingDecision(speaker="rachel", topic_owner="tom"))

    async def run() -> list[str]:
        communicator = _open(user)
        connected, _ = await communicator.connect()
        assert connected
        names = [await communicator.receive_persona_audio()]
        await communicator.send_to(bytes_data=b"student-turn")
        names.append(await communicator.receive_persona_audio())
        names.append(await communicator.receive_persona_audio())
        await communicator.disconnect()
        return names

    assert async_to_sync(run)() == ["Rachel", "Rachel", "Tom"]
