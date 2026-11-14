import pytest

from apps.llm.constants import ModelCategory
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.llm.services.factory import AudioClient
from apps.usage.models import ModelUsage
from apps.voice.services import tts
from apps.voice.tests.test_pcm_stream import pcm, split, wav_header

pytestmark = pytest.mark.django_db


class _FakeStreamingResponse:
    def __init__(self, chunks, fail_after: int | None, error: Exception | None):
        self._chunks = chunks
        self._fail_after = fail_after
        self._error = error
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.closed = True
        return False

    def iter_bytes(self):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index == self._fail_after:
                raise self._error
            yield chunk


class _FakeStreamingSpeech:
    def __init__(self, chunks, *, fail_after: int | None = None, error: Exception | None = None):
        self.chunks = chunks
        self.fail_after = fail_after
        self.error = error
        self.calls = []
        self.responses = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = _FakeStreamingResponse(self.chunks, self.fail_after, self.error)
        self.responses.append(response)
        return response


class _FakeSpeechNamespace:
    def __init__(self, speech):
        self.with_streaming_response = speech


class _FakeAudioNamespace:
    def __init__(self, speech):
        self.speech = _FakeSpeechNamespace(speech)


class _FakeGroqClient:
    def __init__(self, speech):
        self.audio = _FakeAudioNamespace(speech)


def _configure(monkeypatch, speech) -> LLMModel:
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
        lambda purpose: AudioClient(
            client=_FakeGroqClient(speech), model_id=model.model_id, model=model
        ),
    )
    return model


def _usage(model: LLMModel) -> list[ModelUsage]:
    return list(ModelUsage.objects.filter(llm_model=model))


def test_the_stream_asks_the_configured_model_for_a_wav_with_the_given_voice(monkeypatch):
    speech = _FakeStreamingSpeech([wav_header() + pcm(100)])
    _configure(monkeypatch, speech)

    list(tts.synthesize_stream("Hello there.", voice="hannah"))

    assert speech.calls == [
        {
            "model": "canopylabs/orpheus-v1-english",
            "voice": "hannah",
            "input": "Hello there.",
            "response_format": "wav",
        }
    ]


def test_the_stream_delivers_the_audio_of_the_provider_aligned_and_without_header(monkeypatch):
    source = pcm(4000)
    speech = _FakeStreamingSpeech(split(wav_header() + source, [701, 1203, 999]))
    _configure(monkeypatch, speech)

    stream = tts.synthesize_stream("Hello there.", voice="hannah")
    chunks = list(stream)

    assert b"".join(chunks) == source
    assert all(len(chunk) % 2 == 0 for chunk in chunks)
    assert stream.total_bytes == len(source)
    assert speech.responses[0].closed


def test_a_finished_stream_records_the_characters_as_one_successful_use(monkeypatch):
    speech = _FakeStreamingSpeech([wav_header() + pcm(100)])
    model = _configure(monkeypatch, speech)

    list(tts.synthesize_stream("Hello there.", voice="hannah"))

    [usage] = _usage(model)
    assert usage.failed is False
    assert usage.characters == len("Hello there.")


def test_a_provider_failure_in_the_middle_is_recorded_as_failed_and_reraised(monkeypatch):
    speech = _FakeStreamingSpeech(
        split(wav_header() + pcm(4000), [701, 1203]), fail_after=3, error=RuntimeError("connection lost")
    )
    model = _configure(monkeypatch, speech)

    with pytest.raises(RuntimeError, match="connection lost"):
        list(tts.synthesize_stream("Hello there.", voice="hannah"))

    [usage] = _usage(model)
    assert usage.failed is True
    assert usage.characters == 0
    assert speech.responses[0].closed


def test_a_stream_the_session_gives_up_on_is_still_billed_and_the_provider_connection_closed(
    monkeypatch,
):
    speech = _FakeStreamingSpeech(split(wav_header() + pcm(4000), [701, 1203]))
    model = _configure(monkeypatch, speech)

    stream = iter(tts.synthesize_stream("Hello there.", voice="hannah"))
    next(stream)
    stream.close()

    [usage] = _usage(model)
    assert usage.failed is False
    assert usage.characters == len("Hello there.")
    assert speech.responses[0].closed


def test_a_provider_that_sends_no_audio_is_a_failure_and_is_recorded_as_such(monkeypatch):
    speech = _FakeStreamingSpeech([wav_header()])
    model = _configure(monkeypatch, speech)

    with pytest.raises(tts.EmptySpeechStream):
        list(tts.synthesize_stream("Hello there.", voice="hannah"))

    [usage] = _usage(model)
    assert usage.failed is True
