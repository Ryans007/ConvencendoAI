from django.contrib import admin

from apps.llm.constants import ModelCategory
from apps.llm.models import LLMModel

_PRICE_FIELDS_BY_CATEGORY = {
    ModelCategory.CHAT: ("input_price_per_million_tokens", "output_price_per_million_tokens"),
    ModelCategory.STT: ("price_per_audio_hour", "min_billed_audio_seconds"),
    ModelCategory.TTS: ("price_per_million_characters",),
}


@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    """Modelos cadastráveis de cada provedor, escolhíveis na configuração de papéis.

    O preço, em dólar, serve para estimar o custo de cada chamada. Ao editar um modelo, o
    admin mostra só os campos de preço da categoria dele; na criação mostra todos, porque a
    categoria ainda está sendo escolhida na mesma tela.
    """

    list_display = [
        "display_name",
        "model_id",
        "provider",
        "category",
        "structured_output_method",
        "is_active",
    ]
    list_filter = ["category", "is_active", "provider"]
    search_fields = ["display_name", "model_id"]
    autocomplete_fields = ["provider"]

    def get_fieldsets(self, request, obj=None):
        base = (
            None,
            {
                "fields": (
                    "provider",
                    "category",
                    "model_id",
                    "display_name",
                    "structured_output_method",
                    "is_active",
                )
            },
        )
        if obj is None:
            price_fields = tuple(
                field for fields in _PRICE_FIELDS_BY_CATEGORY.values() for field in fields
            )
        else:
            price_fields = _PRICE_FIELDS_BY_CATEGORY[obj.category]
        return [base, ("Preço (US$)", {"fields": price_fields})]
