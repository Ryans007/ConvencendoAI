from django.db import models

from apps.llm.models.llm_provider import LLMProvider


class LLMModel(models.Model):
    """Modelo servido por um provedor, identificado como a API dele espera em `model`."""

    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE, related_name="models")
    model_id = models.CharField(max_length=120)
    display_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "model_id"], name="unique_provider_model_id"
            )
        ]
        ordering = ["provider", "display_name"]

    def __str__(self) -> str:
        return f"{self.provider} · {self.display_name}"
