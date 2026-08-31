from django.utils import timezone

from apps.agents.graph.builder import run_scenario as run_graph
from apps.agents.services.evaluator import evaluate
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.constants import RubricDimension
from apps.catalog.models import Level, Scenario
from apps.progress.constants import is_passing_score
from apps.progress.models import Attempt, AttemptCriterion, ScoreBreakdown
from apps.progress.services.memory import track_memory
from apps.progress.services.scoring import final_score, objective_score


def run_and_record_attempt(user, scenario: Scenario, level: Level) -> Attempt:
    """Executa um cenário do início ao fim e persiste o resultado como uma tentativa.

    É o ponto de encontro entre o núcleo conversacional e a progressão: o núcleo não
    sabe que existe um `Attempt`, e a progressão não sabe que existe um grafo.
    """
    content = load_scenario_content(scenario, level)
    memory = track_memory(user, scenario)

    attempt = Attempt.objects.create(user=user, scenario=scenario, level=level)

    final_state = run_graph(content, memory)
    messages = list(final_state.get("messages") or [])
    outcome = evaluate(content, messages)

    attempt_criteria = [
        AttemptCriterion(
            code=criterion.code,
            text_at_time=criterion.text,
            met=criterion.code in outcome.confirmed_criteria,
        )
        for criterion in content.criteria
    ]

    objective_weight = content.weights.get(RubricDimension.OBJECTIVE, 0)
    breakdowns = [
        ScoreBreakdown(
            dimension=RubricDimension.OBJECTIVE,
            value=int(round(objective_score(attempt_criteria, objective_weight))),
            weight_at_time=objective_weight,
        )
    ] + [
        ScoreBreakdown(
            dimension=judged.dimension,
            value=judged.value,
            weight_at_time=judged.weight,
        )
        for judged in outcome.judged_dimensions
    ]

    score = int(round(final_score(breakdowns)))

    attempt.final_score = score
    attempt.passed = is_passing_score(score)
    attempt.memory_summary = outcome.memory_summary
    attempt.feedback = outcome.feedback
    attempt.completed_at = timezone.now()
    attempt.save()

    for breakdown in breakdowns:
        breakdown.attempt = attempt
    ScoreBreakdown.objects.bulk_create(breakdowns)

    for criterion in attempt_criteria:
        criterion.attempt = attempt
    AttemptCriterion.objects.bulk_create(attempt_criteria)

    return attempt
