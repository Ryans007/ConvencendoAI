from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.usage.models import AccessLimits, LiveSessionLease
from apps.usage.services.session_limits import (
    DAILY_SESSION_LIMIT,
    SESSION_ALREADY_OPEN,
    SessionRefused,
    open_session_lease,
    release_session_lease,
    turn_audio_limit_bytes,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="maria")


def _attempts(user, count: int, days_ago: int = 0) -> None:
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    for _ in range(count):
        attempt = Attempt.objects.create(user=user, scenario=scenario, level=level)
        if days_ago:
            Attempt.objects.filter(pk=attempt.pk).update(
                started_at=timezone.now() - timedelta(days=days_ago)
            )


def test_the_first_session_opens_and_a_second_is_refused(student):
    open_session_lease(student)

    with pytest.raises(SessionRefused) as refusal:
        open_session_lease(student)

    assert refusal.value.code == SESSION_ALREADY_OPEN


def test_releasing_frees_the_next_session(student):
    lease = open_session_lease(student)

    release_session_lease(lease)

    assert open_session_lease(student) is not None


def test_releasing_nothing_is_harmless():
    release_session_lease(None)


def test_an_expired_lease_does_not_count_and_is_removed(student):
    LiveSessionLease.objects.create(user=student, expires_at=timezone.now() - timedelta(seconds=1))

    lease = open_session_lease(student)

    assert LiveSessionLease.objects.filter(user=student).count() == 1
    assert LiveSessionLease.objects.get().pk == lease.pk


def test_the_leases_of_another_student_do_not_count(student, django_user_model):
    other = django_user_model.objects.create_user(username="joao")
    open_session_lease(other)

    assert open_session_lease(student) is not None


def test_the_daily_ceiling_counts_only_todays_attempts(student):
    _attempts(student, 19)
    _attempts(student, 10, days_ago=2)

    assert open_session_lease(student) is not None


def test_the_twentieth_attempt_of_the_day_closes_the_ceiling(student):
    _attempts(student, 20)

    with pytest.raises(SessionRefused) as refusal:
        open_session_lease(student)

    assert refusal.value.code == DAILY_SESSION_LIMIT
    assert not LiveSessionLease.objects.exists()


def test_the_limits_come_from_the_configuration(student):
    limits = AccessLimits.get_solo()
    limits.max_open_voice_sessions = 2
    limits.max_voice_sessions_per_day = 3
    limits.max_turn_audio_kb = 4
    limits.save()

    open_session_lease(student)
    open_session_lease(student)
    with pytest.raises(SessionRefused):
        open_session_lease(student)
    assert turn_audio_limit_bytes() == 4 * 1024
    _attempts(student, 3)
    release_session_lease(LiveSessionLease.objects.first())
    with pytest.raises(SessionRefused) as refusal:
        open_session_lease(student)
    assert refusal.value.code == DAILY_SESSION_LIMIT
