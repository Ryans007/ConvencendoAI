from django.contrib import admin
from django.http import HttpRequest

from apps.usage.models import ModelUsage
from apps.usage.services.usage_totals import usage_totals


@admin.register(ModelUsage)
class ModelUsageAdmin(admin.ModelAdmin):
    """Auditoria do uso de modelos: consulta para o superuser, sem edição.

    Cada linha é uma chamada do sistema a um modelo de IA, com o dono, o consumo e o custo
    estimado com o preço do momento. No topo da lista, os totais valem para o recorte
    filtrado. Só o superuser vê esta tela: o gasto de cada aluno não é para a equipe em geral.
    """

    change_list_template = "admin/usage/modelusage/change_list.html"
    list_display = [
        "created_at",
        "owner",
        "purpose",
        "model_id_at_time",
        "input_tokens",
        "output_tokens",
        "billed_audio_seconds",
        "characters",
        "cost_usd",
        "priced",
        "failed",
    ]
    list_filter = [
        "purpose",
        ("user", admin.RelatedOnlyFieldListFilter),
        ("llm_model", admin.RelatedOnlyFieldListFilter),
        "failed",
        "priced",
    ]
    search_fields = ["username_at_time", "model_id_at_time"]
    date_hierarchy = "created_at"
    list_select_related = ["user", "attempt", "review_item"]

    @admin.display(description="aluno", ordering="username_at_time")
    def owner(self, obj: ModelUsage) -> str:
        return obj.username_at_time or "sistema"

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def changelist_view(self, request: HttpRequest, extra_context=None):
        """Acrescenta os totais do recorte filtrado ao topo da lista."""
        response = super().changelist_view(request, extra_context)
        context = getattr(response, "context_data", None)
        if context is not None and "cl" in context:
            context["usage_totals"] = usage_totals(context["cl"].queryset)
        return response
