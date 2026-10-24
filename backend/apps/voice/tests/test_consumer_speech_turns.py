import json

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.progress.models import SpeechTurn
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.services.stt import SpokenWord, Transcription
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

_TIMED = Transcription(
    "I need one more week.",
    (
        SpokenWord("I", 1.0, 1.2),
        SpokenWord("need", 1.2, 1.5),
        SpokenWord("one", 1.5, 1.7),
        SpokenWord("more", 1.7, 1.9),
        SpokenWord("week.", 1.9, 2.4),
    ),
)


class _ScriptedPersonaLLM:
    def __init__(self, *turns: PersonaTurn):
        self._turns = iter(turns)

    def invoke(self, messages):
        return next(self._turns)


class _NobodyAddressed:
    def invoke(self, messages):
        return RoutingDecision(speaker="")


async def _keep_the_test_connection() -> None:
    """Evita que o Channels feche a conexão do banco do teste a cada mensagem recebida."""


def _prepare(monkeypatch, transcription: Transcription = _TIMED) -> None:
    monkeypatch.setattr("channels.consumer.aclose_old_connections", _keep_the_test_connection)
    persona = _ScriptedPersonaLLM(
        PersonaTurn(line="Why do you need more time?", pass_to="student"),
        PersonaTurn(line="And what is your plan?", pass_to="student"),
    )
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _NobodyAddressed()
    )
    monkeypatch.setattr(voice_consumers, "transcribe_with_words", lambda audio: transcription)
    monkeypatch.setattr(voice_consumers, "synthesize", lambda text, voice: b"fake-wav-bytes")
    monkeypatch.setattr(voice_consumers, "suggest_answer", lambda content, history: "Diga o prazo.")


def _token(django_user_model) -> str:
    user = django_user_model.objects.create(username="aluno")
    return str(AccessToken.for_user(user))


def _answer(token: str, *messages: dict, hints: bool = False) -> list[SpeechTurn]:
    """Abre a sessão, manda as mensagens e um áudio, espera a persona e devolve as vezes."""

    async def run() -> list[SpeechTurn]:
        query = f"token={token}" + ("&hints=1" if hints else "")
        communicator = SessionCommunicator(
            URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?{query}"
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.receive_persona_audio()
        for message in messages:
            await communicator.send_to(text_data=json.dumps(message))
            if message["type"] == "hint_request":
                await communicator.receive_from()
        await communicator.send_to(bytes_data=b"student-audio")
        await communicator.receive_persona_audio()
        turns = await sync_to_async(lambda: list(SpeechTurn.objects.order_by("order")))()
        await communicator.disconnect()
        return turns

    return async_to_sync(run)()


def test_a_turn_is_recorded_with_the_wait_the_browser_sent(django_user_model, monkeypatch):
    _prepare(monkeypatch)

    turns = _answer(_token(django_user_model), {"type": "turn_timing", "waited_ms": 2400})

    assert len(turns) == 1
    turn = turns[0]
    assert turn.order == 1
    assert turn.waited_ms == 2400
    assert turn.leading_silence_ms == 1000
    assert turn.speech_ms == 1400
    assert turn.word_count == 5
    assert turn.text == "I need one more week."
    assert turn.after_hint is False


def test_a_turn_without_a_wait_is_recorded_with_an_unknown_wait(django_user_model, monkeypatch):
    _prepare(monkeypatch)

    turns = _answer(_token(django_user_model))

    assert turns[0].waited_ms is None


@pytest.mark.parametrize("waited_ms", [-5, 11 * 60 * 1000, "2400", True, None])
def test_an_invalid_wait_becomes_unknown(django_user_model, monkeypatch, waited_ms):
    _prepare(monkeypatch)

    turns = _answer(_token(django_user_model), {"type": "turn_timing", "waited_ms": waited_ms})

    assert turns[0].waited_ms is None


def test_a_transcription_without_timed_words_is_not_recorded_and_the_session_goes_on(
    django_user_model, monkeypatch
):
    _prepare(monkeypatch, Transcription("I need one more week."))

    assert _answer(_token(django_user_model)) == []


def test_a_turn_after_a_hint_is_marked(django_user_model, monkeypatch):
    _prepare(monkeypatch)

    turns = _answer(
        _token(django_user_model),
        {"type": "hint_request"},
        {"type": "turn_timing", "waited_ms": 9000},
        hints=True,
    )

    assert turns[0].after_hint is True


def test_a_failure_to_record_the_turn_never_stops_the_session(django_user_model, monkeypatch):
    _prepare(monkeypatch)

    def broken(*args, **kwargs):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(voice_consumers, "record_speech_turn", broken)

    assert _answer(_token(django_user_model)) == []
