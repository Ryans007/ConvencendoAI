import pytest

from apps.llm.constants import ModelCategory
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services.factory import AudioClient
from apps.voice.services import stt

pytestmark = pytest.mark.django_db


class _FakeTranscriptions:
    def __init__(self, text: str = "", error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.text


class _FakeAudio:
    def __init__(self, transcriptions: _FakeTranscriptions):
        self.transcriptions = transcriptions


class _FakeGroqClient:
    def __init__(self, transcriptions: _FakeTranscriptions):
        self.audio = _FakeAudio(transcriptions)


def _configure_stt_model(monkeypatch, fake_client) -> None:
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key_env="LLM_TEST_API_KEY"
    )
    model = LLMModel.objects.create(
        provider=provider,
        category=ModelCategory.STT,
        model_id="whisper-large-v3-turbo",
        display_name="Whisper large v3 turbo",
    )
    config = AgentModelConfig.get_solo()
    config.stt_model = model
    config.save()

    monkeypatch.setattr(
        "apps.voice.services.stt.get_audio_client",
        lambda purpose: AudioClient(client=fake_client, model_id=model.model_id),
    )


def test_transcribe_calls_the_configured_model_and_strips_whitespace(monkeypatch):
    transcriptions = _FakeTranscriptions(text="  hello there  ")
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    result = stt.transcribe(b"raw-audio-bytes")

    assert result == "hello there"
    assert transcriptions.calls[0]["model"] == "whisper-large-v3-turbo"
    assert transcriptions.calls[0]["file"] == ("audio.webm", b"raw-audio-bytes")


def test_transcribe_propagates_provider_errors(monkeypatch):
    transcriptions = _FakeTranscriptions(error=RuntimeError("provider unavailable"))
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        stt.transcribe(b"raw-audio-bytes")
