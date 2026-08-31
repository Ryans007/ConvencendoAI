from django.contrib import admin

from apps.llm.models import LLMModel


@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    """Modelos cadastráveis de cada provedor, escolhíveis na configuração de papéis."""

    list_display = ["display_name", "model_id", "provider", "is_active"]
    list_filter = ["is_active", "provider"]
    search_fields = ["display_name", "model_id"]
    autocomplete_fields = ["provider"]
