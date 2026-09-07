import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt, AttemptCriterion, ScoreBreakdown

pytestmark = pytest.mark.django_db


def _completed_attempt(user) -> Attempt:
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    attempt = Attempt.objects.create(
        user=user,
        scenario=scenario,
        level=level,
        final_score=88,
        passed=True,
        feedback="Bom trabalho explicando o atraso.",
        completed_at=timezone.now(),
    )
    ScoreBreakdown.objects.create(
        attempt=attempt, dimension="objective", value=27, weight_at_time=30
    )
    AttemptCriterion.objects.create(
        attempt=attempt, code="c1", text_at_time="Explicou o motivo técnico", met=True
    )
    return attempt


def test_report_of_own_completed_attempt(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")
    attempt = _completed_attempt(user)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/attempts/{attempt.pk}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["final_score"] == 88
    assert response.data["passed"] is True
    assert response.data["score_breakdowns"][0]["dimension"] == "objective"
    assert response.data["score_breakdowns"][0]["weight"] == 30
    assert response.data["criteria"][0]["code"] == "c1"
    assert response.data["criteria"][0]["met"] is True


def test_report_of_another_users_attempt_is_not_found(django_user_model):
    owner = django_user_model.objects.create_user(username="dono", password="Xk9#mQ2vLp8Z")
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    attempt = _completed_attempt(owner)

    client = APIClient()
    client.force_authenticate(user=other)
    response = client.get(f"/api/attempts/{attempt.pk}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_report_of_attempt_still_in_progress_is_not_found(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    attempt = Attempt.objects.create(user=user, scenario=scenario, level=level)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/attempts/{attempt.pk}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
