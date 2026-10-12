FALLBACK_AUDIO_FORMAT = "webm"

_EBML_MAGIC = b"\x1a\x45\xdf\xa3"


def detect_audio_format(audio: bytes) -> str | None:
    """Descobre o formato de um áudio gravado pelo navegador olhando os primeiros bytes.

    Cada navegador grava num formato: o Chrome e o Firefox em webm, o Safari em mp4. O áudio
    chega ao servidor como bytes puros, sem tipo, então a assinatura do próprio conteúdo é a
    única evidência. Devolve `webm`, `mp4`, `ogg` ou `wav`, ou `None` quando não reconhece.
    """
    if audio.startswith(_EBML_MAGIC):
        return "webm"
    if audio[4:8] == b"ftyp":
        return "mp4"
    if audio.startswith(b"OggS"):
        return "ogg"
    if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
        return "wav"
    return None
