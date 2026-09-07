from django.db import models


class ModelPurpose(models.TextChoices):
    """Os dois papéis de chat do núcleo conversacional que consomem um modelo de LLM."""

    PERSONA = "persona", "Personas"
    JUDGE = "judge", "Avaliador"


class ModelCategory(models.TextChoices):
    """Para que tipo de chamada um `LLMModel` serve.

    Também usada como o papel de `get_audio_client` (`STT` ou `TTS`): cada categoria de
    áudio só tem um papel possível, ao contrário do chat, que tem dois (`ModelPurpose`).
    """

    CHAT = "chat", "Chat"
    STT = "stt", "Transcrição de voz (STT)"
    TTS = "tts", "Síntese de voz (TTS)"
