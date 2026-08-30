from apps.catalog.models import Scenario
from apps.progress.services.selection import best_passed_attempt, latest_attempt


def track_memory(user, before_scenario: Scenario) -> str:
    """Resumo transportado às personas de um cenário: para cada cenário anterior da
    mesma trilha, o resumo da tentativa aprovada de nível mais alto, com recuo para a
    tentativa mais recente quando nenhuma foi aprovada. Escopado à trilha corrente,
    carregado por inteiro — nunca o transcript bruto.
    """
    previous_scenarios = before_scenario.track.scenarios.filter(
        order__lt=before_scenario.order
    ).order_by("order")

    summaries = []
    for scenario in previous_scenarios:
        attempt = best_passed_attempt(user, scenario) or latest_attempt(user, scenario)
        if attempt is not None and attempt.memory_summary:
            summaries.append(attempt.memory_summary)

    return "\n".join(summaries)
