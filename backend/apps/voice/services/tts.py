import time

from apps.llm.constants import ModelCategory
from apps.llm.services.factory import get_audio_client
from apps.usage.services.recording import record_speech_call


def synthesize(text: str, voice: str) -> bytes:
    """Sintetiza a fala de uma persona em áudio, via o modelo de TTS configurado.

    Devolve o WAV pronto exatamente como o provedor entrega — sem decodificar nem
    recodificar, já que ninguém aqui precisa manipular a amostra, só encaminhá-la. O provedor
    não informa o uso, mas cobra pelos caracteres do texto, que são os que enviamos: é isso que
    a chamada, com ou sem falha, grava como uso do modelo.
    """
    resolved = get_audio_client(ModelCategory.TTS)
    started_at = time.monotonic()
    try:
        response = resolved.client.audio.speech.create(
            model=resolved.model_id,
            voice=voice,
            input=text,
            response_format="wav",
        )
        audio = response.read()
    except Exception as exc:
        _record(resolved, len(text), started_at, failed=True, error_code=type(exc).__name__)
        raise
    _record(resolved, len(text), started_at)
    return audio


def _record(resolved, characters: int, started_at: float, **failure) -> None:
    if resolved.model is None:
        return
    record_speech_call(
        llm_model=resolved.model,
        characters=characters,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        **failure,
    )
