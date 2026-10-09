from datetime import date

from django.db.models import OuterRef, Prefetch, QuerySet, Subquery

from apps.review.models import ReviewAnswer, ReviewItem, ReviewOccurrence
from apps.review.services.queries import due_items

ROUND_SIZE = 5


def round_items(user, today: date) -> QuerySet[ReviewItem]:
    """Os itens vencidos do aluno na ordem da rodada, prontos para a tela do item.

    Do vencimento mais antigo para o mais recente e, no mesmo dia, da caixa mais baixa para a
    mais alta: o que o aluno esperou mais, e o que ele sabe menos, vem primeiro. O que o
    aluno disse, a forma correta, a nota, a cena e a data vêm da ocorrência mais recente,
    anotados na própria consulta, e as respostas ainda sem resultado entram por prefetch,
    então o número de consultas não cresce com o tamanho da página.
    """
    latest = ReviewOccurrence.objects.filter(item=OuterRef("pk")).order_by("-created_at", "-id")
    open_answers = ReviewAnswer.objects.filter(result__isnull=True).order_by("created_at", "id")
    return (
        due_items(user, today)
        .annotate(
            latest_produced=Subquery(latest.values("produced")[:1]),
            latest_correct=Subquery(latest.values("correct")[:1]),
            latest_note=Subquery(latest.values("note")[:1]),
            latest_scenario_title=Subquery(latest.values("attempt__scenario__title")[:1]),
            latest_at=Subquery(latest.values("created_at")[:1]),
        )
        .prefetch_related(Prefetch("answers", queryset=open_answers, to_attr="open_answers"))
        .order_by("due_on", "box", "id")
    )
