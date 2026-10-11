from django.contrib import admin

from apps.llm.models import LLMProvider


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    """Provedores de LLM cadastráveis pelo super-admin, sem alteração de código.

    A chave de acesso não é cadastrada aqui: o provedor guarda só o nome da variável de ambiente
    que a contém, e esta tela mostra se ela está definida no servidor. Nenhum caractere do valor
    aparece, nem mascarado, porque qualquer pedaço já é uma pista. Trocar a chave é trocar o
    ambiente do servidor e reiniciar o backend.
    """

    list_display = ["name", "code", "base_url", "api_key_env", "key_status", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    fields = ["name", "code", "base_url", "api_key_env", "key_status", "is_active"]
    readonly_fields = ["key_status"]

    @admin.display(description="chave no ambiente")
    def key_status(self, obj: LLMProvider) -> str:
        return "definida" if obj.has_api_key else "não definida"
