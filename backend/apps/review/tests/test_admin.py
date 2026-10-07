from datetime import date

import pytest
from django.urls import reverse

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.review.models import ReviewItem, ReviewOccurrence

pytestmark = pytest.mark.django_db


def _item(django_user_model) -> ReviewItem:
    user = django_user_model.objects.create(username="aluno_revisado")
    item = ReviewItem.objects.create(
        user=user, rule="past simple with a finished time expression", box=5, due_on=date(2026, 12, 6)
    )
    attempt = Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=3),
    )
    ReviewOccurrence.objects.create(
        item=item,
        attempt=attempt,
        produced="I have worked there yesterday",
        correct="I worked there yesterday",
    )
    return item


def test_the_list_shows_the_items_with_interval_and_mastery(admin_client, django_user_model):
    _item(django_user_model)

    response = admin_client.get(reverse("admin:review_reviewitem_changelist"))

    assert response.status_code == 200
    page = response.content.decode()
    assert "past simple with a finished time expression" in page
    assert "aluno_revisado" in page
    assert "60 dias" in page
    assert "dominado" in page.lower()


def test_the_item_page_shows_its_occurrences(admin_client, django_user_model):
    item = _item(django_user_model)

    response = admin_client.get(reverse("admin:review_reviewitem_change", args=[item.pk]))

    assert response.status_code == 200
    assert "I have worked there yesterday" in response.content.decode()


def test_items_cannot_be_added_changed_or_deleted(admin_client, django_user_model):
    item = _item(django_user_model)

    assert admin_client.get(reverse("admin:review_reviewitem_add")).status_code == 403
    assert admin_client.post(
        reverse("admin:review_reviewitem_change", args=[item.pk]), {"box": 0}
    ).status_code == 403
    assert admin_client.post(
        reverse("admin:review_reviewitem_delete", args=[item.pk]), {"post": "yes"}
    ).status_code == 403
    item.refresh_from_db()
    assert item.box == 5
