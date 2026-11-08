import httpx
import openai
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
        code="groq", name="Groq", base_url="https://api.groq.com/openai/v1", api_key="test-key"
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


_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
_SECRET_SPEECH = b"my-card-number-4111"


def _provider_refusal(code: str) -> openai.BadRequestError:
    response = httpx.Response(400, request=httpx.Request("POST", "https://provider.example/v1"))
    body = {"message": "detalhe do provedor", "type": "invalid_request_error", "code": code}
    return openai.BadRequestError(body["message"], response=response, body=body)


def test_the_file_goes_to_the_provider_with_the_format_it_was_recorded_in(monkeypatch):
    transcriptions = _FakeTranscriptions(text="hello")
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    stt.transcribe(_MP4)

    assert transcriptions.calls[0]["file"] == ("audio.mp4", _MP4)


def test_an_empty_audio_never_reaches_the_provider(monkeypatch):
    transcriptions = _FakeTranscriptions(text="should not be used")
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    assert stt.transcribe(b"") == ""
    assert transcriptions.calls == []


@pytest.mark.parametrize("code", ["empty_audio_file", "invalid_media_file"])
def test_an_audio_the_provider_refuses_as_unusable_is_a_speech_not_heard(monkeypatch, code):
    transcriptions = _FakeTranscriptions(error=_provider_refusal(code))
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    assert stt.transcribe(b"raw-audio-bytes") == ""


def test_a_provider_refusal_that_is_not_about_the_audio_still_fails(monkeypatch):
    transcriptions = _FakeTranscriptions(error=_provider_refusal("model_not_found"))
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    with pytest.raises(openai.BadRequestError):
        stt.transcribe(b"raw-audio-bytes")


def test_the_log_shows_the_size_and_the_format_but_never_the_audio(monkeypatch, capsys):
    transcriptions = _FakeTranscriptions(text="my card number is 4111")
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    stt.transcribe(_MP4 + _SECRET_SPEECH)

    output = capsys.readouterr().out
    assert f"audio recebido: {len(_MP4 + _SECRET_SPEECH)} bytes, formato mp4" in output
    assert _SECRET_SPEECH.decode() not in output
    assert "4111" not in output


def test_an_empty_audio_is_logged_as_zero_bytes(monkeypatch, capsys):
    _configure_stt_model(monkeypatch, _FakeGroqClient(_FakeTranscriptions()))

    stt.transcribe(b"")

    assert "audio recebido: 0 bytes, formato desconhecido" in capsys.readouterr().out


class _VerboseTranscription:
    def __init__(self, text: str, words):
        self.text = text
        self.words = words


class _FakeVerboseTranscriptions(_FakeTranscriptions):
    def __init__(self, response):
        super().__init__()
        self.response = response

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_transcribe_with_words_asks_for_word_timestamps_and_reads_them(monkeypatch):
    response = _VerboseTranscription(
        " I would like ",
        [
            {"word": "I", "start": 0.38, "end": 0.5},
            {"word": "would", "start": 0.5, "end": 0.8},
            {"word": "like", "start": 0.8, "end": 1.06},
        ],
    )
    transcriptions = _FakeVerboseTranscriptions(response)
    _configure_stt_model(monkeypatch, _FakeGroqClient(transcriptions))

    result = stt.transcribe_with_words(b"raw-audio-bytes")

    assert transcriptions.calls[0]["timestamp_granularities"] == ["word"]
    assert result.text == "I would like"
    assert result.words == (
        stt.SpokenWord("I", 0.38, 0.5),
        stt.SpokenWord("would", 0.5, 0.8),
        stt.SpokenWord("like", 0.8, 1.06),
    )


def test_words_given_as_objects_are_read_too(monkeypatch):
    class _Word:
        def __init__(self, word, start, end):
            self.word, self.start, self.end = word, start, end

    response = _VerboseTranscription("hello", [_Word("hello", 0.1, 0.4)])
    _configure_stt_model(monkeypatch, _FakeGroqClient(_FakeVerboseTranscriptions(response)))

    assert stt.transcribe_with_words(b"audio").words == (stt.SpokenWord("hello", 0.1, 0.4),)


def test_incomplete_words_are_skipped(monkeypatch):
    response = _VerboseTranscription(
        "a b c d",
        [
            {"word": "a", "start": 0.0, "end": 0.2},
            {"word": "", "start": 0.2, "end": 0.3},
            {"word": "c", "start": None, "end": 0.5},
            {"word": "d", "start": 0.9, "end": 0.6},
        ],
    )
    _configure_stt_model(monkeypatch, _FakeGroqClient(_FakeVerboseTranscriptions(response)))

    assert stt.transcribe_with_words(b"audio").words == (stt.SpokenWord("a", 0.0, 0.2),)


def test_a_provider_without_words_gives_a_transcription_without_words(monkeypatch):
    _configure_stt_model(monkeypatch, _FakeGroqClient(_FakeTranscriptions(text="hello")))

    result = stt.transcribe_with_words(b"audio")

    assert result == stt.Transcription(text="hello")


def test_an_empty_audio_is_a_transcription_without_text_or_words(monkeypatch):
    _configure_stt_model(monkeypatch, _FakeGroqClient(_FakeTranscriptions()))

    assert stt.transcribe_with_words(b"") == stt.Transcription(text="")
