from django.contrib import admin

from apps.llm.models import LLMProvider


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    """Provedores de LLM cadastráveis pelo super-admin, sem alteração de código."""

    list_display = ["name", "code", "base_url", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
