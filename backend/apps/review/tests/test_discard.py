from datetime import date

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.review.models import ReviewAnswer, ReviewItem, ReviewResultKind

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 7)


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


@pytest.fixture
def client(student):
    api_client = APIClient()
    api_client.force_authenticate(user=student)
    return api_client


def _item(user, box: int = 2) -> ReviewItem:
    return ReviewItem.objects.create(user=user, rule="regra", box=box, due_on=TODAY)


def _url(item: ReviewItem) -> str:
    return f"/api/review/items/{item.pk}/discard/"


def test_discarding_archives_the_item_without_touching_the_calendar(client, student):
    item = _item(student, box=2)

    response = client.post(_url(item))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    item.refresh_from_db()
    assert item.archived_at is not None
    assert (item.box, item.due_on) == (2, TODAY)
    result = item.results.get()
    assert result.outcome == ReviewResultKind.DISCARDED
    assert (result.box_before, result.box_after, result.due_on_after) == (2, 2, None)


def test_discarding_closes_the_open_answers_with_the_discarded_result(client, student):
    item = _item(student)
    answer = ReviewAnswer.objects.create(
        item=item, step=1, attempt=1, heard="x", correct=True, feedback="ok"
    )

    client.post(_url(item))

    answer.refresh_from_db()
    assert answer.result == item.results.get()


def test_a_discarded_item_leaves_the_due_count(client, student):
    item = _item(student)
    assert client.get("/api/review/summary/").data["due"] == 1

    client.post(_url(item))

    assert client.get("/api/review/summary/").data["due"] == 0


def test_discarding_an_archived_item_is_not_found(client, student):
    item = _item(student)
    client.post(_url(item))

    response = client.post(_url(item))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert item.results.count() == 1


def test_discarding_another_students_item_is_not_found_and_changes_nothing(
    client, django_user_model
):
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    item = _item(other)

    response = client.post(_url(item))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    item.refresh_from_db()
    assert item.archived_at is None


def test_discarding_requires_authentication(student):
    item = _item(student)

    response = APIClient().post(_url(item))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
