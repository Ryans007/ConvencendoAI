import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt

pytestmark = pytest.mark.django_db


def _attempt(django_user_model) -> Attempt:
    user = django_user_model.objects.create(username="aluno_auditado")
    return Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="negociar-prazo"),
        level=Level.objects.get(order=2),
        final_score=74,
        passed=True,
        completed_at=timezone.now(),
        hints_enabled=True,
        hints_used=2,
    )


def test_attempt_list_shows_the_hints_columns(admin_client, django_user_model):
    _attempt(django_user_model)

    response = admin_client.get(reverse("admin:progress_attempt_changelist"))

    assert response.status_code == 200
    page = response.content.decode()
    assert "dicas ligadas" in page.lower()
    assert "dicas usadas" in page.lower()
    assert "aluno_auditado" in page


def test_attempts_cannot_be_added_changed_or_deleted_in_the_admin(admin_client, django_user_model):
    attempt = _attempt(django_user_model)

    assert admin_client.get(reverse("admin:progress_attempt_add")).status_code == 403
    assert admin_client.post(
        reverse("admin:progress_attempt_change", args=[attempt.pk]), {"hints_used": 0}
    ).status_code == 403
    assert admin_client.post(
        reverse("admin:progress_attempt_delete", args=[attempt.pk]), {"post": "yes"}
    ).status_code == 403
    attempt.refresh_from_db()
    assert attempt.hints_used == 2
