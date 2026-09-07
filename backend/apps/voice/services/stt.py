from apps.llm.constants import ModelCategory
from apps.llm.services.factory import get_audio_client


def transcribe(audio: bytes) -> str:
    """Transcreve um turno de áudio do aluno para texto, via o modelo de STT configurado.

    O nome do arquivo diz `.webm` porque é o formato que o `MediaRecorder` do navegador
    produz por padrão — o provedor de STT identifica o contêiner pelo conteúdo, não
    exige que o áudio seja convertido para WAV antes de chegar aqui.
    """
    resolved = get_audio_client(ModelCategory.STT)
    transcription = resolved.client.audio.transcriptions.create(
        file=("audio.webm", audio),
        model=resolved.model_id,
        language="en",
        response_format="text",
    )
    return str(transcription).strip()
