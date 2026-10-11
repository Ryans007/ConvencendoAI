from django.db import models

from apps.llm.constants import ModelCategory, StructuredOutputMethod
from apps.llm.models.llm_provider import LLMProvider


class LLMModel(models.Model):
    """Modelo servido por um provedor, identificado como a API dele espera em `model`.

    `structured_output_method` só vale para modelos de chat: o suporte ao modo estrito
    varia de provedor para provedor e até de modelo para modelo, então a escolha é do
    cadastro, e não global.
    """

    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE, related_name="models")
    category = models.CharField(
        max_length=10, choices=ModelCategory.choices, default=ModelCategory.CHAT
    )
    model_id = models.CharField(max_length=120)
    display_name = models.CharField(max_length=120)
    structured_output_method = models.CharField(
        "método de saída estruturada",
        max_length=20,
        choices=StructuredOutputMethod.choices,
        default=StructuredOutputMethod.TOOL_CALLING,
        help_text=(
            "Como o modelo devolve fala, dica e decisões em formato fixo. 'JSON schema "
            "estrito' elimina as recusas do provedor por saída fora do formato, mas só "
            "funciona em provedores e modelos que o suportam (por exemplo, os gpt-oss da "
            "Groq); na dúvida, deixe 'Chamada de ferramenta'."
        ),
    )
    is_active = models.BooleanField(default=True)
    input_price_per_million_tokens = models.DecimalField(
        "preço por 1M de tokens de entrada (US$)",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Só para modelos de chat.",
    )
    output_price_per_million_tokens = models.DecimalField(
        "preço por 1M de tokens de saída (US$)",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Só para modelos de chat. O raciocínio do modelo conta como saída.",
    )
    price_per_audio_hour = models.DecimalField(
        "preço por hora de áudio (US$)",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Só para modelos de transcrição de voz (STT).",
    )
    min_billed_audio_seconds = models.PositiveSmallIntegerField(
        "segundos mínimos cobrados por pedido",
        default=0,
        help_text=(
            "Só para STT. Alguns provedores cobram um mínimo por pedido, mesmo para uma fala "
            "mais curta; o Whisper do Groq cobra 10 segundos."
        ),
    )
    price_per_million_characters = models.DecimalField(
        "preço por 1M de caracteres (US$)",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Só para modelos de síntese de voz (TTS).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "model_id"], name="unique_provider_model_id"
            )
        ]
        ordering = ["provider", "display_name"]

    def __str__(self) -> str:
        return f"{self.provider} · {self.display_name}"
