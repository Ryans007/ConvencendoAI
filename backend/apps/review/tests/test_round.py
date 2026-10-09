from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.review.models import ReviewAnswer, ReviewItem, ReviewOccurrence

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


@pytest.fixture
def client(student):
    api_client = APIClient()
    api_client.force_authenticate(user=student)
    return api_client


def _item(
    user, *, due_days_ago: int = 0, box: int = 0, rule: str = "regra", archived: bool = False
) -> ReviewItem:
    item = ReviewItem.objects.create(
        user=user,
        rule=rule,
        box=box,
        due_on=TODAY - timedelta(days=due_days_ago),
        archived_at=timezone.now() if archived else None,
    )
    attempt = Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=3),
    )
    ReviewOccurrence.objects.create(
        item=item,
        attempt=attempt,
        produced=f"disse {rule}",
        correct=f"correto {rule}",
    )
    return item


def _round(client) -> dict:
    response = client.get("/api/review/round/")
    assert response.status_code == status.HTTP_200_OK
    return response.data


def test_the_round_is_ordered_by_oldest_due_date_then_lowest_box(client, student):
    newest = _item(student, due_days_ago=1, rule="newest")
    oldest_high_box = _item(student, due_days_ago=5, box=3, rule="oldest-high")
    oldest_low_box = _item(student, due_days_ago=5, box=0, rule="oldest-low")

    ids = [item["id"] for item in _round(client)["results"]]

    assert ids == [oldest_low_box.id, oldest_high_box.id, newest.id]


def test_the_round_has_five_items_and_reports_the_total(client, student):
    for index in range(7):
        _item(student, due_days_ago=10 - index, rule=f"r{index}")

    data = _round(client)

    assert data["count"] == 7
    assert len(data["results"]) == 5
    assert [item["said"] for item in data["results"]][0] == "disse r0"


def test_the_second_page_has_the_rest(client, student):
    for index in range(7):
        _item(student, due_days_ago=10 - index, rule=f"r{index}")

    response = client.get("/api/review/round/?page=2")

    assert len(response.data["results"]) == 2


def test_items_not_due_archived_or_from_another_student_stay_out(
    client, student, django_user_model
):
    due = _item(student, rule="due")
    ReviewItem.objects.create(user=student, rule="later", box=0, due_on=TODAY + timedelta(days=1))
    _item(student, rule="archived", archived=True)
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    _item(other, rule="other")

    ids = [item["id"] for item in _round(client)["results"]]

    assert ids == [due.id]


def test_a_new_item_starts_at_step_one_without_the_correct_form(client, student):
    _item(student, box=2)

    item = _round(client)["results"][0]

    assert (item["step"], item["attempt"], item["correct"]) == (1, 1, "")
    assert item["said"] == "disse regra"
    assert item["scenario_title"]
    assert item["interval_days"] == 7
    assert item["mastered"] is False


def test_an_interrupted_item_resumes_at_step_two_with_the_correct_form(client, student):
    item = _item(student)
    ReviewAnswer.objects.create(
        item=item, step=1, attempt=1, heard="x", correct=True, feedback="ok"
    )

    result = _round(client)["results"][0]

    assert (result["step"], result["attempt"]) == (2, 1)
    assert result["correct"] == "correto regra"


def test_a_wrong_first_attempt_resumes_at_step_one_attempt_two(client, student):
    item = _item(student)
    ReviewAnswer.objects.create(
        item=item, step=1, attempt=1, heard="x", correct=False, feedback="pista"
    )

    result = _round(client)["results"][0]

    assert (result["step"], result["attempt"], result["correct"]) == (1, 2, "")


def test_the_latest_occurrence_is_the_example(client, student):
    item = _item(student)
    attempt = item.occurrences.get().attempt
    ReviewOccurrence.objects.create(
        item=item, attempt=attempt, produced="mais recente", correct="certo recente"
    )

    assert _round(client)["results"][0]["said"] == "mais recente"


def test_a_mastered_item_is_flagged(client, student):
    _item(student, box=5)

    assert _round(client)["results"][0]["mastered"] is True


def test_the_round_requires_authentication():
    assert APIClient().get("/api/review/round/").status_code == status.HTTP_401_UNAUTHORIZED


def test_the_number_of_queries_does_not_grow_with_the_items(client, student):
    _item(student, rule="a")
    with CaptureQueriesContext(connection) as small:
        client.get("/api/review/round/")

    for index in range(4):
        item = _item(student, rule=f"b{index}")
        ReviewAnswer.objects.create(
            item=item, step=1, attempt=1, heard="x", correct=True, feedback="ok"
        )
    with CaptureQueriesContext(connection) as big:
        client.get("/api/review/round/")

    assert len(big.captured_queries) == len(small.captured_queries)


def test_the_item_carries_the_note_of_its_latest_occurrence(client, student):
    item = _item(student)
    occurrence = item.occurrences.get()
    occurrence.note = "Repare no tempo da frase: ele já terminou."
    occurrence.save()

    assert _round(client)["results"][0]["note"] == "Repare no tempo da frase: ele já terminou."


def test_an_old_item_without_a_note_comes_back_with_an_empty_note(client, student):
    _item(student)

    result = _round(client)["results"][0]

    assert result["note"] == ""
    assert result["said"] == "disse regra"


def test_the_note_comes_with_the_first_attempt(client, student):
    item = _item(student)
    occurrence = item.occurrences.get()
    occurrence.note = "Uma nota."
    occurrence.save()

    result = _round(client)["results"][0]

    assert (result["step"], result["attempt"], result["note"]) == (1, 1, "Uma nota.")


def test_the_newest_occurrence_decides_which_note_is_shown(client, student):
    item = _item(student)
    older = item.occurrences.get()
    older.note = "Nota antiga."
    older.save()
    ReviewOccurrence.objects.create(
        item=item, attempt=older.attempt, produced="novo", correct="certo", note="Nota nova."
    )

    assert _round(client)["results"][0]["note"] == "Nota nova."
