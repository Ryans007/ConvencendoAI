import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt

pytestmark = pytest.mark.django_db


def test_journey_requires_authentication():
    client = APIClient()

    response = client.get("/api/journey/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_journey_reflects_the_authenticated_users_attempts(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")
    scenario = Scenario.objects.get(slug="entrevista-de-emprego")
    level = Level.objects.get(order=3)
    Attempt.objects.create(
        user=user,
        scenario=scenario,
        level=level,
        final_score=90,
        passed=True,
        completed_at=timezone.now(),
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/journey/")

    assert response.status_code == status.HTTP_200_OK
    track = next(t for t in response.data if t["slug"] == scenario.track.slug)
    scenario_state = next(
        s for s in track["scenario_states"] if s["slug"] == "entrevista-de-emprego"
    )
    assert scenario_state["completed"] is True
    level_state = next(l for l in scenario_state["level_states"] if l["order"] == 3)
    assert level_state["approved"] is True


def test_two_authenticated_users_see_different_journeys(django_user_model):
    user_a = django_user_model.objects.create_user(username="aluno_a", password="Xk9#mQ2vLp8Z")
    user_b = django_user_model.objects.create_user(username="aluno_b", password="Xk9#mQ2vLp8Z")
    scenario = Scenario.objects.get(slug="entrevista-de-emprego")
    level = Level.objects.get(order=3)
    Attempt.objects.create(
        user=user_a,
        scenario=scenario,
        level=level,
        final_score=90,
        passed=True,
        completed_at=timezone.now(),
    )

    client = APIClient()

    client.force_authenticate(user=user_a)
    response_a = client.get("/api/journey/")
    track_a = next(t for t in response_a.data if t["slug"] == scenario.track.slug)
    scenario_a = next(s for s in track_a["scenario_states"] if s["slug"] == scenario.slug)

    client.force_authenticate(user=user_b)
    response_b = client.get("/api/journey/")
    track_b = next(t for t in response_b.data if t["slug"] == scenario.track.slug)
    scenario_b = next(s for s in track_b["scenario_states"] if s["slug"] == scenario.slug)

    assert scenario_a["completed"] is True
    assert scenario_b["completed"] is False
