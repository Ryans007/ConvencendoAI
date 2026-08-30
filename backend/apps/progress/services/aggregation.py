from apps.catalog.models import Level, Track
from apps.progress.models import Attempt
from apps.progress.services.selection import best_passed_attempt


def track_depth(user, track: Track) -> tuple[int, int]:
    """Níveis aprovados sobre níveis possíveis: quantas combinações de cenário e
    nível da trilha o aluno já aprovou, sobre o total de combinações possíveis.
    """
    scenarios = list(track.scenarios.all())
    possible = len(scenarios) * Level.objects.count()
    approved = (
        Attempt.objects.filter(user=user, scenario__in=scenarios, passed=True)
        .values("scenario_id", "level_id")
        .distinct()
        .count()
    )
    return approved, possible


def track_performance(user, track: Track) -> float | None:
    """Média das notas da tentativa aprovada de nível mais alto de cada cenário
    concluído da trilha. `None` quando nenhum cenário está concluído ainda.
    """
    scores = [
        attempt.final_score
        for scenario in track.scenarios.all()
        if (attempt := best_passed_attempt(user, scenario)) is not None
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)
