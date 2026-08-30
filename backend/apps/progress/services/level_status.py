from datetime import timedelta

from django.utils import timezone

from apps.progress.models import Attempt


def is_level_approved(user, scenario, level) -> bool:
    """Um nível está aprovado quando existe, para este aluno, alguma tentativa com
    `passed=True` naquele par de cenário e nível. A aprovação é permanente: uma
    tentativa posterior com nota inferior não desfaz.
    """
    return Attempt.objects.filter(
        user=user, scenario=scenario, level=level, passed=True
    ).exists()


def cooldown_remaining(user, scenario, level) -> timedelta | None:
    """Tempo restante até este par de cenário e nível ficar disponível de novo, ou
    `None` se já estiver liberado.
    """
    last_completed = (
        Attempt.objects.filter(
            user=user, scenario=scenario, level=level, completed_at__isnull=False
        )
        .order_by("-completed_at")
        .values_list("completed_at", flat=True)
        .first()
    )
    if last_completed is None:
        return None

    release_at = last_completed + timedelta(hours=scenario.cooldown_hours)
    remaining = release_at - timezone.now()
    return remaining if remaining > timedelta(0) else None


def is_level_available(user, scenario, level) -> bool:
    """Um nível está disponível quando não há cooldown ativo sobre ele — os três
    níveis são sempre selecionáveis, sem depender de aprovação em outro.
    """
    return cooldown_remaining(user, scenario, level) is None
