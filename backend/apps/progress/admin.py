from django.contrib import admin

from apps.progress.models import Attempt, SpeechTurn


class SpeechTurnInline(admin.TabularInline):
    """As vezes de fala da tentativa, só para leitura: são a base das medidas de fluência."""

    model = SpeechTurn
    extra = 0
    can_delete = False
    fields = [
        "order",
        "waited_ms",
        "leading_silence_ms",
        "speech_ms",
        "word_count",
        "long_pauses",
        "after_hint",
        "text",
    ]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    """Auditoria das tentativas: consulta, sem edição.

    A tentativa é o registro do que o aluno fez e de como foi avaliado; editá-la à mão
    apagaria a história que a nota conta. Por isso a tela só lista e detalha, inclusive o
    uso das dicas, que não entra na nota.
    """

    list_display = [
        "id",
        "user",
        "scenario",
        "level",
        "final_score",
        "passed",
        "hints_enabled",
        "hints_used",
        "ended_by",
        "completed_at",
    ]
    list_filter = ["scenario", "level", "passed", "hints_enabled"]
    search_fields = ["user__username"]
    list_select_related = ["user", "scenario", "level"]
    inlines = [SpeechTurnInline]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
