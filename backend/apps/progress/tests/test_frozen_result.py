import pytest

from apps.catalog.models import Criterion, Level, Scenario, Track
from apps.progress.models import Attempt, AttemptCriterion


@pytest.mark.django_db
def test_reescrever_criterio_nao_altera_tentativa_anterior(django_user_model) -> None:
    """Reescrever o texto de um critério não altera nenhuma tentativa anterior."""
    track = Track.objects.create(slug="t", title="T", order=900, student_role="dev backend")
    scenario = Scenario.objects.create(
        track=track,
        slug="s",
        title="S",
        order=1,
        objective="objetivo",
        context="contexto",
        closing_hint="Wrap up the scene.",
    )
    level = Level.objects.get(order=1)
    criterion = Criterion.objects.create(scenario=scenario, code="c1", text="Texto original", order=1)
    criterion.levels.add(level)

    user = django_user_model.objects.create(username="aluno")
    attempt = Attempt.objects.create(
        user=user, scenario=scenario, level=level, final_score=68, passed=False
    )
    AttemptCriterion.objects.create(
        attempt=attempt, code="c1", text_at_time=criterion.text, met=False
    )

    criterion.text = "Texto reescrito depois da tentativa"
    criterion.save()

    snapshot = attempt.criteria.get(code="c1")
    assert snapshot.text_at_time == "Texto original"
    assert attempt.final_score == 68
