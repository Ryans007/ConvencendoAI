from datetime import date

from django.db.models import QuerySet

from apps.agents.services.evaluator import MAX_REVIEW_ITEMS
from apps.review.models import ReviewItem, ReviewOccurrence


def active_items(user) -> QuerySet[ReviewItem]:
    """Os itens de revisão do aluno que ainda contam: os não arquivados.

    O item arquivado por "Não disse isso" continua no banco, para a auditoria, mas sai do
    resumo, das rodadas e de qualquer contagem, então toda consulta de itens do aluno parte
    daqui.
    """
    return ReviewItem.objects.filter(user=user, archived_at__isnull=True)


def due_items(user, today: date) -> QuerySet[ReviewItem]:
    """Os itens ativos do aluno que vencem hoje ou já passaram da data."""
    return active_items(user).filter(due_on__lte=today)


def attempt_mistakes(attempt) -> list[ReviewOccurrence]:
    """Os erros de uma sessão que o relatório mostra, na ordem em que foram gravados.

    Fica fora o erro cujo item o aluno arquivou com "Não disse isso": ele disse que não falou
    aquilo, e o relatório não pode continuar dizendo que falou. São no máximo 4, o limite de
    erros que uma sessão grava.
    """
    occurrences = ReviewOccurrence.objects.filter(
        attempt=attempt, item__archived_at__isnull=True
    ).order_by("id")
    return list(occurrences[:MAX_REVIEW_ITEMS])
