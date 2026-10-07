from django.contrib import admin

from apps.review.models import ReviewItem, ReviewOccurrence
from apps.review.services.schedule import BOX_INTERVAL_DAYS, is_mastered


class ReviewOccurrenceInline(admin.TabularInline):
    """As vezes em que o aluno errou na regra, com a tentativa de origem."""

    model = ReviewOccurrence
    fields = ["produced", "correct", "attempt", "created_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ReviewItem)
class ReviewItemAdmin(admin.ModelAdmin):
    """Auditoria dos itens de revisão: consulta, sem edição.

    Os itens nascem da avaliação das sessões e mudam com as revisões do aluno; editá-los à
    mão mudaria o calendário dele sem nenhuma resposta que justificasse. Por isso a tela só
    lista e detalha, com as ocorrências de cada item.
    """

    list_display = ["rule", "user", "interval", "due_on", "mastered", "updated_at"]
    list_filter = ["box", "due_on"]
    search_fields = ["user__username", "rule"]
    list_select_related = ["user"]
    inlines = [ReviewOccurrenceInline]

    @admin.display(description="intervalo")
    def interval(self, obj: ReviewItem) -> str:
        return f"{BOX_INTERVAL_DAYS[min(obj.box, len(BOX_INTERVAL_DAYS) - 1)]} dias"

    @admin.display(description="dominado", boolean=True)
    def mastered(self, obj: ReviewItem) -> bool:
        return is_mastered(obj.box)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
