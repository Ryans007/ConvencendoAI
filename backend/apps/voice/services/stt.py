import time

from apps.llm.constants import ModelCategory
from apps.llm.services.factory import get_audio_client
from apps.usage.services.recording import record_transcription_call


def transcribe(audio: bytes) -> str:
    """Transcreve um turno de áudio do aluno para texto, via o modelo de STT configurado.

    O nome do arquivo diz `.webm` porque é o formato que o `MediaRecorder` do navegador
    produz por padrão — o provedor de STT identifica o contêiner pelo conteúdo, não
    exige que o áudio seja convertido para WAV antes de chegar aqui.

    Pede `verbose_json` porque só nesse formato o provedor devolve a duração do áudio, que é
    a base da cobrança; o texto é o mesmo. Se o provedor não informar a duração, a
    transcrição segue normalmente e o uso fica sem os segundos. A chamada, com ou sem falha, é
    gravada como uso do modelo.
    """
    resolved = get_audio_client(ModelCategory.STT)
    started_at = time.monotonic()
    try:
        transcription = resolved.client.audio.transcriptions.create(
            file=("audio.webm", audio),
            model=resolved.model_id,
            language="en",
            response_format="verbose_json",
        )
    except Exception as exc:
        _record(resolved, None, started_at, failed=True, error_code=type(exc).__name__)
        raise
    duration = getattr(transcription, "duration", None)
    _record(resolved, duration, started_at)
    return str(getattr(transcription, "text", transcription)).strip()


def _record(resolved, audio_seconds, started_at: float, **failure) -> None:
    if resolved.model is None:
        return
    record_transcription_call(
        llm_model=resolved.model,
        audio_seconds=audio_seconds,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        **failure,
    )
