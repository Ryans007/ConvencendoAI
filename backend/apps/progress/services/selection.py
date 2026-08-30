from apps.progress.models import Attempt


def best_passed_attempt(user, scenario) -> Attempt | None:
    """A tentativa aprovada de nível mais alto de um cenário, ou `None` se nenhuma foi
    aprovada. É a mesma seleção usada tanto para a nota que o cenário contribui à
    trilha quanto para a memória transportada ao cenário seguinte.
    """
    return (
        Attempt.objects.filter(user=user, scenario=scenario, passed=True)
        .select_related("level")
        .order_by("-level__order", "-completed_at")
        .first()
    )


def latest_attempt(user, scenario) -> Attempt | None:
    """A tentativa mais recente de um cenário, aprovada ou não."""
    return (
        Attempt.objects.filter(user=user, scenario=scenario)
        .order_by("-completed_at", "-started_at")
        .first()
    )
