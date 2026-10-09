from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.review.models import ReviewItem
from apps.review.services.summary import review_summary

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 7)


def _item(user, due_on: date, rule: str = "rule") -> ReviewItem:
    return ReviewItem.objects.create(user=user, rule=rule, box=0, due_on=due_on)


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


def test_items_due_today_or_before_count_and_the_next_one_is_reported(student):
    _item(student, TODAY - timedelta(days=3))
    _item(student, TODAY - timedelta(days=1))
    _item(student, TODAY)
    _item(student, TODAY + timedelta(days=5))
    _item(student, TODAY + timedelta(days=2))

    summary = review_summary(student, TODAY)

    assert summary.due == 3
    assert summary.next_due_on == TODAY + timedelta(days=2)


def test_an_item_due_tomorrow_is_not_due_yet(student):
    _item(student, TODAY + timedelta(days=1))

    summary = review_summary(student, TODAY)

    assert summary.due == 0
    assert summary.next_due_on == TODAY + timedelta(days=1)


def test_a_student_without_items_has_nothing_due(student):
    summary = review_summary(student, TODAY)

    assert summary.due == 0
    assert summary.next_due_on is None


def test_another_students_items_do_not_count(student, django_user_model):
    other = django_user_model.objects.create(username="outro")
    _item(other, TODAY - timedelta(days=1))
    _item(other, TODAY + timedelta(days=1))

    summary = review_summary(student, TODAY)

    assert (summary.due, summary.next_due_on) == (0, None)


def test_the_api_returns_the_summary_of_the_authenticated_student(student):
    today = timezone.localdate()
    _item(student, today)
    _item(student, today + timedelta(days=4))

    client = APIClient()
    client.force_authenticate(user=student)
    response = client.get("/api/review/summary/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {
        "due": 1,
        "next_due_on": (today + timedelta(days=4)).isoformat(),
    }


def test_the_api_returns_null_when_nothing_is_scheduled(student):
    client = APIClient()
    client.force_authenticate(user=student)

    response = client.get("/api/review/summary/")

    assert response.data == {"due": 0, "next_due_on": None}


def test_the_api_requires_authentication():
    response = APIClient().get("/api/review/summary/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_archived_items_do_not_count_as_due_or_as_the_next_one(student):
    ReviewItem.objects.create(
        user=student, rule="a", box=0, due_on=TODAY, archived_at=timezone.now()
    )
    ReviewItem.objects.create(
        user=student,
        rule="b",
        box=0,
        due_on=TODAY + timedelta(days=2),
        archived_at=timezone.now(),
    )
    _item(student, TODAY - timedelta(days=1))
    _item(student, TODAY + timedelta(days=4))

    summary = review_summary(student, TODAY)

    assert summary.due == 1
    assert summary.next_due_on == TODAY + timedelta(days=4)
