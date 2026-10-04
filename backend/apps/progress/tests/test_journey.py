from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Level, Scenario, Track
from apps.progress.models import Attempt
from apps.progress.services import LevelState, build_journey


@pytest.fixture
def levels(db) -> list[Level]:
    return list(Level.objects.filter(order__in=(1, 2, 3)))


def _scenario(track: Track, slug: str, order: int) -> Scenario:
    return Scenario.objects.create(
        track=track,
        slug=slug,
        title=slug,
        order=order,
        objective="objetivo",
        context="contexto",
        closing_hint="Wrap up the scene.",
    )


@pytest.mark.django_db
def test_leitura_da_jornada_nao_cresce_com_o_numero_de_cenarios(
    django_user_model, levels: list[Level]
) -> None:
    """A quantidade de consultas para montar a jornada inteira não cresce com o
    número de trilhas e cenários existentes.
    """
    user = django_user_model.objects.create(username="aluno")
    track_a = Track.objects.create(slug="a", title="A", order=900, student_role="dev backend")
    _scenario(track_a, "a1", 1)
    _scenario(track_a, "a2", 2)

    with CaptureQueriesContext(connection) as small:
        build_journey(user)

    track_b = Track.objects.create(slug="b", title="B", order=901, student_role="hóspede")
    for i in range(10):
        _scenario(track_b, f"b{i}", i + 1)

    with CaptureQueriesContext(connection) as big:
        build_journey(user)

    assert len(big.captured_queries) == len(small.captured_queries)


def _level_state(user, level_order: int, scenario_slug: str = "entrevista-de-emprego") -> LevelState:
    for track_state in build_journey(user):
        for scenario_state in track_state.scenario_states:
            if scenario_state.scenario.slug == scenario_slug:
                return next(
                    state
                    for state in scenario_state.level_states
                    if state.level.order == level_order
                )
    raise AssertionError(f"cenário {scenario_slug} fora da jornada")


def _attempt(
    user,
    level_order: int,
    *,
    score: int,
    passed: bool,
    completed_ago: timedelta | None,
    scenario_slug: str = "entrevista-de-emprego",
) -> Attempt:
    return Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug=scenario_slug),
        level=Level.objects.get(order=level_order),
        final_score=score if completed_ago is not None else None,
        passed=passed if completed_ago is not None else None,
        completed_at=None if completed_ago is None else timezone.now() - completed_ago,
    )


@pytest.mark.django_db
def test_nivel_com_uma_tentativa_concluida_traz_essa_tentativa(django_user_model) -> None:
    user = django_user_model.objects.create(username="aluno")
    attempt = _attempt(user, 1, score=82, passed=True, completed_ago=timedelta(days=2))

    last = _level_state(user, 1).last_attempt

    assert last == attempt
    assert (last.final_score, last.passed) == (82, True)


@pytest.mark.django_db
def test_vale_a_tentativa_mais_recente_mesmo_reprovada(django_user_model) -> None:
    user = django_user_model.objects.create(username="aluno")
    _attempt(user, 1, score=90, passed=True, completed_ago=timedelta(days=3))
    failed_later = _attempt(user, 1, score=40, passed=False, completed_ago=timedelta(days=1))

    state = _level_state(user, 1)

    assert state.last_attempt == failed_later
    assert state.approved is True


@pytest.mark.django_db
def test_tentativa_abandonada_nao_conta(django_user_model) -> None:
    user = django_user_model.objects.create(username="aluno")
    concluded = _attempt(user, 2, score=75, passed=True, completed_ago=timedelta(days=2))
    _attempt(user, 2, score=0, passed=False, completed_ago=None)
    only_abandoned = _attempt(user, 3, score=0, passed=False, completed_ago=None)

    assert _level_state(user, 2).last_attempt == concluded
    assert only_abandoned.completed_at is None
    assert _level_state(user, 3).last_attempt is None


@pytest.mark.django_db
def test_nivel_nunca_tentado_traz_nulo(django_user_model) -> None:
    user = django_user_model.objects.create(username="aluno")
    _attempt(user, 1, score=82, passed=True, completed_ago=timedelta(days=2))

    assert _level_state(user, 2).last_attempt is None
    assert _level_state(user, 3).last_attempt is None


@pytest.mark.django_db
def test_tentativa_de_outro_aluno_nao_aparece(django_user_model) -> None:
    owner = django_user_model.objects.create(username="dono")
    other = django_user_model.objects.create(username="outro")
    _attempt(owner, 1, score=82, passed=True, completed_ago=timedelta(days=2))

    assert _level_state(other, 1).last_attempt is None


@pytest.mark.django_db
def test_a_tentativa_de_outro_cenario_ou_nivel_nao_vaza(django_user_model) -> None:
    user = django_user_model.objects.create(username="aluno")
    _attempt(user, 1, score=82, passed=True, completed_ago=timedelta(days=2))

    assert _level_state(user, 1, "negociar-prazo").last_attempt is None
    assert _level_state(user, 3).last_attempt is None


@pytest.mark.django_db
def test_cooldown_continua_vindo_da_ultima_tentativa_concluida(django_user_model) -> None:
    user = django_user_model.objects.create(username="aluno")
    _attempt(user, 1, score=82, passed=True, completed_ago=timedelta(hours=2))

    remaining = _level_state(user, 1).cooldown_remaining

    assert remaining is not None
    assert timedelta(hours=9, minutes=50) < remaining <= timedelta(hours=10)
    assert _level_state(user, 2).cooldown_remaining is None
