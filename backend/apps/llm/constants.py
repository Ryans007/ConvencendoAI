from django.db import models


PROVIDER_TIMEOUT_SECONDS = 30
PROVIDER_MAX_RETRIES = 1


class ModelPurpose(models.TextChoices):
    """Os papéis de chat do núcleo conversacional que consomem um modelo de LLM."""

    PERSONA = "persona", "Personas"
    JUDGE = "judge", "Avaliador"
    ROUTER = "router", "Roteador de turno"


class ModelCategory(models.TextChoices):
    """Para que tipo de chamada um `LLMModel` serve.

    Também usada como o papel de `get_audio_client` (`STT` ou `TTS`): cada categoria de
    áudio só tem um papel possível, ao contrário do chat, que tem três (`ModelPurpose`).
    """

    CHAT = "chat", "Chat"
    STT = "stt", "Transcrição de voz (STT)"
    TTS = "tts", "Síntese de voz (TTS)"


class StructuredOutputMethod(models.TextChoices):
    """Como um modelo de chat produz saída estruturada (fala, dica, decisão de roteamento).

    `TOOL_CALLING` transforma o schema numa ferramenta obrigatória, e o modelo decide
    chamá-la: funciona em qualquer provedor, mas o modelo às vezes responde em texto e o
    provedor recusa. `JSON_SCHEMA_STRICT` faz o provedor restringir a geração ao schema,
    o que elimina essa recusa, mas nem todo provedor e modelo o suporta.
    """

    TOOL_CALLING = "tool_calling", "Chamada de ferramenta"
    JSON_SCHEMA_STRICT = "json_schema_strict", "JSON schema estrito"
