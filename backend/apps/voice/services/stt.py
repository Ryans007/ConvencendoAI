import time

import openai

from apps.llm.constants import ModelCategory
from apps.llm.services.factory import get_audio_client
from apps.usage.services.recording import record_transcription_call
from apps.voice.services.audio_format import FALLBACK_AUDIO_FORMAT, detect_audio_format

UNUSABLE_AUDIO_CODES = frozenset({"empty_audio_file", "invalid_media_file"})


def _is_unusable_audio(exc: BaseException) -> bool:
    """O provedor recusou o áudio por estar vazio ou por não ser um arquivo de mídia válido."""
    return isinstance(exc, openai.BadRequestError) and exc.code in UNUSABLE_AUDIO_CODES


def transcribe(audio: bytes) -> str:
    """Transcreve um turno de áudio do aluno para texto, via o modelo de STT configurado.

    O arquivo vai ao provedor com o formato que o próprio áudio mostra ter (webm, mp4, ogg ou
    wav), porque cada navegador grava num formato — o Safari em mp4 — e o provedor se guia
    pelo nome do arquivo. Sem conversão para WAV. Um formato não reconhecido segue como webm.

    Um áudio sem nenhum byte, ou que o provedor recusa por estar vazio ou por não ser mídia
    válida, devolve texto vazio, que quem chama já trata como fala não ouvida: é um problema da
    gravação, e não do provedor, e não pode encerrar a sessão do aluno. O áudio vazio nem chega
    ao provedor. O log registra o tamanho e o formato recebidos, nunca o áudio nem o texto.

    Pede `verbose_json` porque só nesse formato o provedor devolve a duração do áudio, que é
    a base da cobrança; o texto é o mesmo. Se o provedor não informar a duração, a
    transcrição segue normalmente e o uso fica sem os segundos. A chamada, com ou sem falha, é
    gravada como uso do modelo.
    """
    audio_format = detect_audio_format(audio)
    print(f"[stt] audio recebido: {len(audio)} bytes, formato {audio_format or 'desconhecido'}")
    if not audio:
        return ""
    resolved = get_audio_client(ModelCategory.STT)
    started_at = time.monotonic()
    try:
        transcription = resolved.client.audio.transcriptions.create(
            file=(f"audio.{audio_format or FALLBACK_AUDIO_FORMAT}", audio),
            model=resolved.model_id,
            language="en",
            response_format="verbose_json",
        )
    except Exception as exc:
        _record(resolved, None, started_at, failed=True, error_code=type(exc).__name__)
        if _is_unusable_audio(exc):
            print("[stt] provedor recusou o audio como vazio ou invalido; o aluno fala de novo")
            return ""
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
