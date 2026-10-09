from django.contrib import admin

from apps.review.models import ReviewAnswer, ReviewOccurrence, ReviewResult


class ReadOnlyInline(admin.TabularInline):
    """Base das linhas de auditoria: só mostram, nunca criam, alteram nem apagam."""

    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ReviewOccurrenceInline(ReadOnlyInline):
    """As vezes em que o aluno errou na regra, com a tentativa de origem."""

    model = ReviewOccurrence
    fields = ["produced", "correct", "note", "attempt", "created_at"]
    readonly_fields = fields


class ReviewAnswerInline(ReadOnlyInline):
    """Cada resposta falada da revisão: o que foi ouvido, o veredito e o feedback.

    É o que permite conferir se o professor julgou bem, como as tentativas de cenário
    permitem conferir o avaliador.
    """

    model = ReviewAnswer
    fields = [
        "step",
        "attempt",
        "heard",
        "correct",
        "feedback",
        "correction",
        "revealed_correct",
        "result",
        "created_at",
    ]
    readonly_fields = fields


class ReviewResultInline(ReadOnlyInline):
    """O resultado de cada revisão terminada, com a caixa antes e depois."""

    model = ReviewResult
    fields = ["outcome", "box_before", "box_after", "due_on_after", "finished_at"]
    readonly_fields = fields
