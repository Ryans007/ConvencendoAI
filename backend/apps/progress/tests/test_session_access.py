from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.progress.services import build_journey
from apps.progress.services.session_access import (
    LEVEL_IN_COOLDOWN,
    SCENARIO_LOCKED,
    session_access_denial,
)

pytestmark = pytest.mark.django_db

_INTERVIEW = "entrevista-de-emprego"
_NEGOTIATION = "negociar-prazo"
_HOTEL = "problema-no-quarto"


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="maria", password="Xk9#mQ2vLp8Z")


def _attempt(
    user,
    slug: str,
    level: int = 1,
    *,
    passed: bool | None = None,
    hours_ago: float | None = None,
) -> Attempt:
    """Uma tentativa; sem `hours_ago` ela fica abandonada, sem avaliação."""
    attempt = Attempt.objects.create(
        user=user, scenario=Scenario.objects.get(slug=slug), level=Level.objects.get(order=level)
    )
    if hours_ago is not None:
        attempt.final_score = 80 if passed else 40
        attempt.passed = passed
        attempt.completed_at = timezone.now() - timedelta(hours=hours_ago)
        attempt.save()
    return attempt


def _denial(user, slug: str, level: int = 1):
    return session_access_denial(
        user, Scenario.objects.get(slug=slug), Level.objects.get(order=level)
    )


def test_the_first_scenario_of_the_first_track_is_open_to_a_new_student(student):
    assert _denial(student, _INTERVIEW) is None


def test_a_scenario_whose_previous_one_is_not_completed_is_locked(student):
    denial = _denial(student, _NEGOTIATION)

    assert denial.code == SCENARIO_LOCKED
    assert denial.retry_after_seconds is None


def test_a_scenario_of_a_track_whose_previous_track_is_not_completed_is_locked(student):
    _attempt(student, _INTERVIEW, passed=True, hours_ago=20)

    assert _denial(student, _HOTEL).code == SCENARIO_LOCKED


def test_completing_the_previous_scenario_unlocks_the_next_one(student):
    _attempt(student, _INTERVIEW, passed=True, hours_ago=20)

    assert _denial(student, _NEGOTIATION) is None


def test_completing_the_whole_previous_track_unlocks_the_next_track(student):
    _attempt(student, _INTERVIEW, passed=True, hours_ago=20)
    _attempt(student, _NEGOTIATION, passed=True, hours_ago=20)

    assert _denial(student, _HOTEL) is None


def test_a_failed_attempt_does_not_unlock_the_next_scenario(student):
    _attempt(student, _INTERVIEW, passed=False, hours_ago=20)

    assert _denial(student, _NEGOTIATION).code == SCENARIO_LOCKED


def test_a_level_completed_two_hours_ago_is_in_cooldown_with_the_time_left(student):
    hours = Scenario.objects.get(slug=_INTERVIEW).cooldown_hours
    _attempt(student, _INTERVIEW, passed=False, hours_ago=2)

    denial = _denial(student, _INTERVIEW)

    assert denial.code == LEVEL_IN_COOLDOWN
    expected = (hours - 2) * 3600
    assert abs(denial.retry_after_seconds - expected) <= 5


def test_another_level_of_the_same_scenario_is_not_in_cooldown(student):
    _attempt(student, _INTERVIEW, level=1, passed=False, hours_ago=2)

    assert _denial(student, _INTERVIEW, level=2) is None


def test_after_the_cooldown_the_level_opens_again(student):
    hours = Scenario.objects.get(slug=_INTERVIEW).cooldown_hours
    _attempt(student, _INTERVIEW, passed=False, hours_ago=hours + 1)

    assert _denial(student, _INTERVIEW) is None


def test_an_abandoned_attempt_does_not_start_a_cooldown(student):
    _attempt(student, _INTERVIEW)

    assert _denial(student, _INTERVIEW) is None


def test_the_cooldown_of_another_student_does_not_apply(student, django_user_model):
    other = django_user_model.objects.create_user(username="joao", password="Xk9#mQ2vLp8Z")
    _attempt(other, _INTERVIEW, passed=False, hours_ago=1)

    assert _denial(student, _INTERVIEW) is None


def test_the_superuser_is_outside_the_rules(django_user_model):
    boss = django_user_model.objects.create_superuser(
        username="chefe", email="c@empresa.com", password="Xk9#mQ2vLp8Z"
    )
    _attempt(boss, _INTERVIEW, passed=False, hours_ago=1)

    assert _denial(boss, _HOTEL) is None
    assert _denial(boss, _INTERVIEW) is None


def test_a_staff_user_who_is_not_superuser_follows_the_journey(django_user_model):
    staff = django_user_model.objects.create_user(
        username="equipe", password="Xk9#mQ2vLp8Z", is_staff=True
    )

    assert _denial(staff, _HOTEL).code == SCENARIO_LOCKED


_STATES = {
    "nothing done": [],
    "interview failed two hours ago": [(_INTERVIEW, 1, False, 2)],
    "interview approved long ago": [(_INTERVIEW, 1, True, 20)],
    "interview approved and negotiation failed recently": [
        (_INTERVIEW, 1, True, 20),
        (_NEGOTIATION, 2, False, 3),
    ],
    "whole career track approved": [(_INTERVIEW, 1, True, 20), (_NEGOTIATION, 1, True, 20)],
    "only an abandoned attempt": [(_INTERVIEW, 1, None, None)],
}


@pytest.mark.parametrize("state", list(_STATES))
def test_the_server_agrees_with_the_journey_for_every_scenario_and_level(student, state):
    for slug, level, passed, hours_ago in _STATES[state]:
        _attempt(student, slug, level, passed=passed, hours_ago=hours_ago)

    scenario_states = {
        scenario_state.scenario.slug: scenario_state
        for track in build_journey(student)
        for scenario_state in track.scenario_states
    }
    assert set(scenario_states) >= {_INTERVIEW, _NEGOTIATION, _HOTEL}

    for slug, scenario_state in scenario_states.items():
        for level_state in scenario_state.level_states:
            denial = _denial(student, slug, level_state.level.order)
            if not scenario_state.unlocked:
                assert denial is not None and denial.code == SCENARIO_LOCKED, (state, slug)
            elif level_state.cooldown_remaining is not None:
                assert denial is not None and denial.code == LEVEL_IN_COOLDOWN, (state, slug)
                journey_seconds = level_state.cooldown_remaining.total_seconds()
                assert abs(denial.retry_after_seconds - journey_seconds) <= 5
            else:
                assert denial is None, (state, slug, level_state.level.order)
