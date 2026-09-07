import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt

pytestmark = pytest.mark.django_db


def test_briefing_without_previous_attempt_has_no_memory(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/scenarios/{scenario.slug}/levels/{level.order}/briefing/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["objective"] == scenario.objective
    assert response.data["memory_summary"] == ""
    assert "criteria" not in response.data
    assert "weights" not in response.data


def test_briefing_with_previous_attempt_includes_memory(django_user_model):
    user = django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")
    previous_scenario = Scenario.objects.get(slug="entrevista-de-emprego")
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    Attempt.objects.create(
        user=user,
        scenario=previous_scenario,
        level=level,
        final_score=90,
        passed=True,
        memory_summary="Trabalha como desenvolvedor backend, gosta de detalhar exemplos.",
        completed_at=timezone.now(),
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/scenarios/{scenario.slug}/levels/{level.order}/briefing/")

    assert response.status_code == status.HTTP_200_OK
    assert "desenvolvedor backend" in response.data["memory_summary"]


def test_briefing_requires_authentication():
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    client = APIClient()

    response = client.get(f"/api/scenarios/{scenario.slug}/levels/{level.order}/briefing/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
