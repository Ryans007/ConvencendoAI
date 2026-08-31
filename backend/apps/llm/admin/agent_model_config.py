from django.contrib import admin
from django.http import HttpRequest

from apps.llm.models import AgentModelConfig


@admin.register(AgentModelConfig)
class AgentModelConfigAdmin(admin.ModelAdmin):
    """Configuração única de qual modelo atende personas e qual atende o avaliador."""

    list_display = ["persona_model", "judge_model"]
    autocomplete_fields = ["persona_model", "judge_model"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not AgentModelConfig.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
