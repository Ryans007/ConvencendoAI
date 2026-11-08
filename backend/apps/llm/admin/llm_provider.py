from django import forms
from django.contrib import admin

from apps.llm.models import LLMProvider


class LLMProviderForm(forms.ModelForm):
    """Formulário do provedor com uma caixa só de escrita para a chave.

    A caixa abre sempre vazia e nunca devolve o que foi digitado, nem quando o formulário volta
    com erro de validação (`render_value=False`). Assim a chave inteira nunca aparece no HTML.
    Deixar a caixa vazia mantém a chave atual.
    """

    new_api_key = forms.CharField(
        required=False,
        strip=True,
        label="Nova chave",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Cole a chave de acesso do provedor. Deixe vazio para manter a chave atual.",
    )

    class Meta:
        model = LLMProvider
        fields = ["name", "code", "base_url", "is_active"]


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    """Provedores de LLM cadastráveis pelo super-admin, sem alteração de código.

    A chave de acesso é colada na caixa "Nova chave" e gravada criptografada. Depois disso, a
    tela só mostra o começo dela ("Chave atual"); para trocá-la, cola-se a nova na mesma caixa.
    """

    form = LLMProviderForm
    list_display = ["name", "code", "base_url", "key_hint", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    fields = ["name", "code", "base_url", "key_hint", "new_api_key", "is_active"]
    readonly_fields = ["key_hint"]

    @admin.display(description="chave atual")
    def key_hint(self, obj: LLMProvider) -> str:
        return obj.api_key_hint or "não definida"

    def save_model(self, request, obj: LLMProvider, form, change: bool) -> None:
        new_key = form.cleaned_data.get("new_api_key")
        if new_key:
            obj.api_key = new_key
        super().save_model(request, obj, form, change)
