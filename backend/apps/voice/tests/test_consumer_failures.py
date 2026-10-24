import json
import logging

import httpx
import openai
import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from rest_framework_simplejwt.tokens import AccessToken

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Scenario
from apps.llm.services.factory import AudioClient
from apps.progress.models import Attempt
from apps.progress.services import build_journey
from apps.voice import consumers as voice_consumers
from apps.voice.routing import websocket_urlpatterns
from apps.voice.services import stt
from apps.voice.services.stt import Transcription
from apps.voice.tests.scene_end import end_after_the_first_turn
from apps.voice.tests.session_client import SessionCommunicator

pytestmark = pytest.mark.django_db

_REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")
_PROVIDER_DETAIL = (
    "Rate limit reached for model `openai/gpt-oss-20b` on tokens per day: "
    "Limit 200000, Used 198775"
)
_OPENING = PersonaTurn(line="Hello, let's talk.", pass_to="student")
_RESOLVING = PersonaTurn(line="Deal, see you next week.", pass_to="student")


def _rate_limit() -> openai.RateLimitError:
    response = httpx.Response(429, request=_REQUEST)
    return openai.RateLimitError(_PROVIDER_DETAIL, response=response, body=None)


class _ScriptedPersonaLLM:
    """Persona falsa: devolve os turnos do roteiro e levanta as exceções do roteiro."""

    def __init__(self, script):
        self._script = iter(script)

    def invoke(self, messages):
        step = next(self._script)
        if isinstance(step, BaseException):
            raise step
        return step


class _NobodyAddressed:
    def invoke(self, messages):
        return RoutingDecision(speaker="")


def _prepare(monkeypatch, persona_script, *, transcribe=None, synthesize=None):
    persona = _ScriptedPersonaLLM(persona_script)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: persona)
    monkeypatch.setattr(
        graph_routing, "get_structured_llm", lambda purpose, schema: _NobodyAddressed()
    )
    monkeypatch.setattr(
        voice_consumers,
        "transcribe_with_words",
        transcribe or (lambda audio: Transcription("I need one more week.")),
    )
    monkeypatch.setattr(
        voice_consumers, "synthesize", synthesize or (lambda text, voice: b"fake-wav-bytes")
    )


def _student(django_user_model):
    user = django_user_model.objects.create(username="aluno")
    return user, str(AccessToken.for_user(user))


async def _connect(token):
    communicator = SessionCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/voice/negociar-prazo/3/?token={token}"
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def _expect_error(communicator, code, forbidden_text=_PROVIDER_DETAIL):
    raw = await communicator.receive_from()
    payload = json.loads(raw)
    assert payload["type"] == "error"
    assert payload["code"] == code
    assert payload["message"]
    assert forbidden_text not in raw
    assert (await communicator.receive_output())["type"] == "websocket.close"


def _attempt_stayed_open(user) -> None:
    attempt = Attempt.objects.get(user=user)
    assert attempt.completed_at is None
    assert attempt.final_score is None
    scenario = Scenario.objects.get(slug="negociar-prazo")
    for track in build_journey(user):
        for scenario_state in track.scenario_states:
            if scenario_state.scenario != scenario:
                continue
            for level_state in scenario_state.level_states:
                assert level_state.last_attempt is None
                assert level_state.cooldown_remaining is None


def test_rate_limit_while_the_persona_speaks_ends_the_session_with_a_code(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    _prepare(monkeypatch, [_OPENING, _rate_limit()])

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()
        await communicator.send_to(bytes_data=b"student-turn")

        await _expect_error(communicator, "provider_rate_limited")
        await sync_to_async(_attempt_stayed_open)(user)
        await communicator.disconnect()

    async_to_sync(run)()


def test_provider_that_does_not_answer_ends_the_session_as_unavailable(
    django_user_model, monkeypatch
):
    _, token = _student(django_user_model)
    _prepare(monkeypatch, [_OPENING, openai.APIConnectionError(request=_REQUEST)])

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()
        await communicator.send_to(bytes_data=b"student-turn")

        await _expect_error(communicator, "provider_unavailable")
        await communicator.disconnect()

    async_to_sync(run)()


def test_unexpected_error_is_reported_and_logged_with_its_traceback(
    django_user_model, monkeypatch, caplog
):
    _, token = _student(django_user_model)
    _prepare(monkeypatch, [_OPENING, ValueError("defeito no código")])

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()
        await communicator.send_to(bytes_data=b"student-turn")

        await _expect_error(communicator, "unexpected", forbidden_text="defeito no código")
        await communicator.disconnect()

    with caplog.at_level(logging.ERROR, logger="apps.voice.consumers"):
        async_to_sync(run)()

    logged = [record for record in caplog.records if record.exc_info]
    assert logged
    assert logged[-1].exc_info[0] is ValueError


def test_evaluation_failure_after_the_scene_is_reported_as_report_failed(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    _prepare(monkeypatch, [_OPENING, _RESOLVING])
    end_after_the_first_turn(monkeypatch)

    def failing_evaluate(content, messages, known_rules=(), speech_metrics=None):
        raise _rate_limit()

    monkeypatch.setattr("apps.agents.services.session_runner.evaluate", failing_evaluate)

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()
        await communicator.send_to(bytes_data=b"student-turn")

        await communicator.receive_persona_audio()
        assert json.loads(await communicator.receive_from()) == {"type": "evaluating"}
        await _expect_error(communicator, "report_failed")
        await sync_to_async(_attempt_stayed_open)(user)
        await communicator.disconnect()

    async_to_sync(run)()


def test_transcription_failure_carries_the_code_too(django_user_model, monkeypatch):
    _, token = _student(django_user_model)

    def failing_transcribe(audio):
        raise _rate_limit()

    _prepare(monkeypatch, [_OPENING], transcribe=failing_transcribe)

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()
        await communicator.send_to(bytes_data=b"student-turn")

        await _expect_error(communicator, "provider_rate_limited")
        await communicator.disconnect()

    async_to_sync(run)()


def test_voice_synthesis_failure_carries_the_code_too(django_user_model, monkeypatch):
    _, token = _student(django_user_model)

    def failing_synthesize(text, voice):
        raise openai.APIConnectionError(request=_REQUEST)

    _prepare(monkeypatch, [_OPENING], synthesize=failing_synthesize)

    async def run() -> None:
        communicator = await _connect(token)

        assert json.loads(await communicator.receive_from()) == {
            "type": "speaker",
            "name": "Rachel",
        }
        await _expect_error(communicator, "provider_unavailable")
        await communicator.disconnect()

    async_to_sync(run)()


def test_an_audio_the_provider_refuses_as_empty_asks_the_student_to_speak_again(
    django_user_model, monkeypatch
):
    user, token = _student(django_user_model)
    refusal_body = {"message": "file is empty", "type": "invalid_request_error"}
    refusal_body["code"] = "empty_audio_file"
    refusal = openai.BadRequestError(
        "file is empty", response=httpx.Response(400, request=_REQUEST), body=refusal_body
    )
    answers = iter([refusal, "I need one more week."])

    class _Transcriptions:
        def create(self, **kwargs):
            answer = next(answers)
            if isinstance(answer, BaseException):
                raise answer
            return answer

    client = type("Client", (), {"audio": type("Audio", (), {"transcriptions": _Transcriptions()})})
    monkeypatch.setattr(
        "apps.voice.services.stt.get_audio_client",
        lambda purpose: AudioClient(client=client, model_id="whisper"),
    )
    _prepare(monkeypatch, [_OPENING, _RESOLVING], transcribe=stt.transcribe_with_words)

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()

        await communicator.send_to(bytes_data=b"RIFF....WAVEempty")
        assert json.loads(await communicator.receive_from()) == {"type": "no_speech"}
        await sync_to_async(_attempt_stayed_open)(user)

        await communicator.send_to(bytes_data=b"real-speech")
        await communicator.receive_persona_audio()
        await communicator.disconnect()

    async_to_sync(run)()


def test_an_empty_audio_frame_asks_the_student_to_speak_again(django_user_model, monkeypatch):
    user, token = _student(django_user_model)
    _prepare(monkeypatch, [_OPENING], transcribe=stt.transcribe_with_words)

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()

        await communicator.send_input({"type": "websocket.receive", "bytes": b""})
        assert json.loads(await communicator.receive_from()) == {"type": "no_speech"}
        await sync_to_async(_attempt_stayed_open)(user)
        await communicator.disconnect()

    async_to_sync(run)()


def test_a_bad_request_that_is_not_about_the_audio_still_ends_the_session(
    django_user_model, monkeypatch
):
    _, token = _student(django_user_model)
    response = httpx.Response(400, request=_REQUEST)
    other = openai.BadRequestError(
        "detalhe", response=response, body={"message": "detalhe", "code": "model_not_found"}
    )

    def failing_transcribe(audio):
        raise other

    _prepare(monkeypatch, [_OPENING], transcribe=failing_transcribe)

    async def run() -> None:
        communicator = await _connect(token)
        await communicator.receive_persona_audio()
        await communicator.send_to(bytes_data=b"student-turn")

        await _expect_error(communicator, "provider_unavailable", forbidden_text="model_not_found")
        await communicator.disconnect()

    async_to_sync(run)()
