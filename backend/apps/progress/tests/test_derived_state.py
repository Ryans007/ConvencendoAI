from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Level, Scenario, Track
from apps.progress.constants import is_passing_score
from apps.progress.models import Attempt
from apps.progress.services import (
    cooldown_remaining,
    is_level_available,
    is_scenario_completed,
    is_scenario_unlocked,
)
from apps.progress.services.selection import best_passed_attempt


@pytest.fixture
def levels(db) -> dict[int, Level]:
    return {n: Level.objects.get(order=n) for n in (1, 2, 3)}


@pytest.fixture
def track(db) -> Track:
    """Ordem 0, antes de qualquer trilha semeada: garante que esta trilha de teste
    seja sempre a primeira, e portanto sempre liberada, independente do estado de
    outras trilhas no banco.
    """
    return Track.objects.create(slug="t", title="T", order=0, student_role="dev backend")


def _scenario(track: Track, slug: str, order: int, cooldown_hours: int = 12) -> Scenario:
    return Scenario.objects.create(
        track=track,
        slug=slug,
        title=slug,
        order=order,
        objective="objetivo",
        context="contexto",
        closing_hint="Wrap up the scene.",
        cooldown_hours=cooldown_hours,
    )


def test_setenta_aprova_e_sessenta_e_nove_nao() -> None:
    """A nota mínima de aprovação é única: 70 passa, 69 não."""
    assert is_passing_score(70) is True
    assert is_passing_score(69) is False


@pytest.mark.django_db
def test_cooldown_atinge_apenas_o_nivel_repetido(django_user_model, track, levels) -> None:
    """O cooldown de uma tentativa afeta só o par (cenário, nível) repetido."""
    scenario = _scenario(track, "s1", 1)
    user = django_user_model.objects.create(username="aluno")
    Attempt.objects.create(
        user=user,
        scenario=scenario,
        level=levels[2],
        final_score=80,
        passed=True,
        completed_at=timezone.now(),
    )

    assert cooldown_remaining(user, scenario, levels[2]) is not None
    assert is_level_available(user, scenario, levels[2]) is False
    assert is_level_available(user, scenario, levels[1]) is True
    assert is_level_available(user, scenario, levels[3]) is True


@pytest.mark.django_db
def test_remover_tentativa_aprovada_recalcula_estado(django_user_model, track, levels) -> None:
    """Remover uma tentativa aprovada recalcula o estado do cenário e do seguinte."""
    scenario_1 = _scenario(track, "s1", 1)
    scenario_2 = _scenario(track, "s2", 2)
    user = django_user_model.objects.create(username="aluno")

    attempt = Attempt.objects.create(
        user=user,
        scenario=scenario_1,
        level=levels[1],
        final_score=80,
        passed=True,
        completed_at=timezone.now(),
    )

    assert is_scenario_completed(user, scenario_1) is True
    assert is_scenario_unlocked(user, scenario_2) is True

    attempt.delete()

    assert is_scenario_completed(user, scenario_1) is False
    assert is_scenario_unlocked(user, scenario_2) is False


@pytest.mark.django_db
def test_praticar_nivel_facil_nao_sobrescreve_memoria_do_nivel_mais_alto(
    django_user_model, track, levels
) -> None:
    """A memória vem da tentativa aprovada de nível mais alto, mesmo se o aluno
    praticar depois um nível mais fácil já dominado.
    """
    scenario = _scenario(track, "s1", 1)
    user = django_user_model.objects.create(username="aluno")
    now = timezone.now()

    Attempt.objects.create(
        user=user,
        scenario=scenario,
        level=levels[3],
        final_score=90,
        passed=True,
        memory_summary="Domina o nível 3.",
        completed_at=now,
    )
    Attempt.objects.create(
        user=user,
        scenario=scenario,
        level=levels[1],
        final_score=95,
        passed=True,
        memory_summary="Praticou o nível fácil de novo.",
        completed_at=now + timedelta(hours=1),
    )

    selected = best_passed_attempt(user, scenario)

    assert selected.level.order == 3
    assert selected.memory_summary == "Domina o nível 3."
