import pytest

from apps.llm.constants import ModelCategory
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services.factory import AudioClient
from apps.voice.services import tts

pytestmark = pytest.mark.django_db


class _FakeResponse:
    def __init__(self, audio: bytes):
        self._audio = audio

    def read(self) -> bytes:
        return self._audio


class _FakeSpeech:
    def __init__(self, audio: bytes = b"", error: Exception | None = None):
        self.audio = audio
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return _FakeResponse(self.audio)


class _FakeAudioNamespace:
    def __init__(self, speech: _FakeSpeech):
        self.speech = speech


class _FakeGroqClient:
    def __init__(self, speech: _FakeSpeech):
        self.audio = _FakeAudioNamespace(speech)


def _configure_tts_model(monkeypatch, fake_client) -> None:
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key="test-key"
    )
    model = LLMModel.objects.create(
        provider=provider,
        category=ModelCategory.TTS,
        model_id="canopylabs/orpheus-v1-english",
        display_name="Orpheus",
    )
    config = AgentModelConfig.get_solo()
    config.tts_model = model
    config.save()

    monkeypatch.setattr(
        "apps.voice.services.tts.get_audio_client",
        lambda purpose: AudioClient(client=fake_client, model_id=model.model_id),
    )


def test_synthesize_calls_the_configured_model_with_the_given_voice(monkeypatch):
    speech = _FakeSpeech(audio=b"wav-bytes")
    _configure_tts_model(monkeypatch, _FakeGroqClient(speech))

    result = tts.synthesize("Hello there.", voice="hannah")

    assert result == b"wav-bytes"
    assert speech.calls[0]["model"] == "canopylabs/orpheus-v1-english"
    assert speech.calls[0]["voice"] == "hannah"
    assert speech.calls[0]["input"] == "Hello there."
    assert speech.calls[0]["response_format"] == "wav"


def test_synthesize_propagates_provider_errors(monkeypatch):
    speech = _FakeSpeech(error=RuntimeError("terms not accepted"))
    _configure_tts_model(monkeypatch, _FakeGroqClient(speech))

    with pytest.raises(RuntimeError, match="terms not accepted"):
        tts.synthesize("Hello there.", voice="hannah")
