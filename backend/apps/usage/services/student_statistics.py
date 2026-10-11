from dataclasses import dataclass
from datetime import datetime

from django.db.models import Avg, Count, Max, Q, QuerySet, Sum

from apps.progress.models import Attempt
from apps.review.models import ReviewAnswer, ReviewResult
from apps.review.models.review_result import ReviewResultKind
from apps.usage.services.usage_totals import month_start, month_usage_annotations

_COMPLETED = Q(attempts__completed_at__isnull=False)

_HITS = (ReviewResultKind.FIRST_TRY, ReviewResultKind.SECOND_TRY)


@dataclass(frozen=True)
class StudentStatistics:
    """As estatísticas de uso de um aluno, calculadas na leitura a partir do que já está gravado.

    Uma sessão concluída é uma tentativa com resultado gravado; a abandonada é a que foi
    iniciada e nunca chegou à avaliação. Na revisão, um item revisado é um resultado que não
    foi descartado, e o acerto é o item revisado que o aluno acertou de primeira ou na segunda
    tentativa.
    """

    sessions_started: int
    sessions_completed: int
    sessions_abandoned: int
    scenarios_practiced: int
    levels_practiced: int
    average_score: float | None
    approvals: int
    hints_used: int
    review_answers: int
    review_items_reviewed: int
    review_hits: int
    last_activity: datetime | None


def student_statistics(user) -> StudentStatistics:
    """Calcula as estatísticas de um aluno, para a tela de detalhe dele no admin."""
    attempts = Attempt.objects.filter(user=user)
    totals = attempts.aggregate(
        started=Count("id"),
        completed=Count("id", filter=Q(completed_at__isnull=False)),
        scenarios=Count("scenario", distinct=True),
        average=Avg("final_score", filter=Q(completed_at__isnull=False)),
        approvals=Count("id", filter=Q(passed=True)),
        hints=Sum("hints_used"),
        last_attempt=Max("started_at"),
    )
    levels = attempts.values("scenario", "level").distinct().count()

    answers = ReviewAnswer.objects.filter(item__user=user)
    answer_totals = answers.aggregate(count=Count("id"), last=Max("created_at"))
    results = ReviewResult.objects.filter(item__user=user).exclude(
        outcome=ReviewResultKind.DISCARDED
    )
    result_totals = results.aggregate(
        reviewed=Count("id"), hits=Count("id", filter=Q(outcome__in=_HITS))
    )

    activity = [t for t in (totals["last_attempt"], answer_totals["last"]) if t is not None]
    return StudentStatistics(
        sessions_started=totals["started"],
        sessions_completed=totals["completed"],
        sessions_abandoned=totals["started"] - totals["completed"],
        scenarios_practiced=totals["scenarios"],
        levels_practiced=levels,
        average_score=totals["average"],
        approvals=totals["approvals"],
        hints_used=totals["hints"] or 0,
        review_answers=answer_totals["count"],
        review_items_reviewed=result_totals["reviewed"],
        review_hits=result_totals["hits"],
        last_activity=max(activity) if activity else None,
    )


def annotate_list_statistics(users: QuerySet) -> QuerySet:
    """Acrescenta à lista de usuários as colunas de uso, numa consulta só.

    Só a relação com as tentativas entra na consulta, então as contagens distintas e a média
    não se multiplicam por outras junções. Os tokens e o custo do mês vêm de subconsultas, para
    o uso de modelos não multiplicar as linhas das tentativas. As colunas de revisão ficam para
    o detalhe, que calcula por aluno.
    """
    return users.annotate(
        **month_usage_annotations(month_start()),
        sessions_started=Count("attempts", distinct=True),
        sessions_completed=Count("attempts", filter=_COMPLETED, distinct=True),
        scenarios_practiced=Count("attempts__scenario", distinct=True),
        average_score=Avg("attempts__final_score", filter=_COMPLETED),
    )
