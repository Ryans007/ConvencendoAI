from datetime import date

from django.db.models import QuerySet

from apps.review.models import ReviewItem


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
