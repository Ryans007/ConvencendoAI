from django.db import models


class UsagePurpose(models.TextChoices):
    """Para que o sistema chamou um modelo: os papéis de chat mais a voz."""

    PERSONA = "persona", "Persona"
    JUDGE = "judge", "Avaliador"
    ROUTER = "router", "Roteador de turno"
    TRANSCRIPTION = "stt", "Transcrição de voz"
    SPEECH = "tts", "Síntese de voz"
