from django.contrib import admin
from django.http import HttpRequest

from apps.llm.models import AgentModelConfig


@admin.register(AgentModelConfig)
class AgentModelConfigAdmin(admin.ModelAdmin):
    """Configuração única de qual modelo atende cada papel e qual voz toca na revisão."""

    list_display = [
        "persona_model",
        "judge_model",
        "stt_model",
        "tts_model",
        "router_model",
        "review_voice",
    ]
    autocomplete_fields = ["persona_model", "judge_model", "stt_model", "tts_model", "router_model"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not AgentModelConfig.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
