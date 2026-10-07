from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Min, Q

from apps.review.models import ReviewItem


@dataclass(frozen=True)
class ReviewSummary:
    """Quantos itens do aluno estão vencidos e quando vence o próximo dos que ainda não."""

    due: int
    next_due_on: date | None


def review_summary(user, today: date) -> ReviewSummary:
    """Resume a revisão do aluno numa consulta só, comparando as datas no momento da leitura.

    Vencido é o item que vence hoje ou já passou da data. O vencimento é calculado aqui, e
    não por uma tarefa agendada que marque os itens, pela mesma razão do cooldown: o sistema
    não tem fila nem job, e uma comparação de datas na leitura basta.
    """
    totals = ReviewItem.objects.filter(user=user).aggregate(
        due=Count("id", filter=Q(due_on__lte=today)),
        next_due_on=Min("due_on", filter=Q(due_on__gt=today)),
    )
    return ReviewSummary(due=totals["due"], next_due_on=totals["next_due_on"])
