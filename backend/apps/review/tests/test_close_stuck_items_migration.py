import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.review.models import ReviewAnswer, ReviewItem, ReviewOccurrence, ReviewResultKind

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
migration = importlib.import_module("apps.review.migrations.0004_close_items_stuck_after_step_one")


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


def _item(user, *, box: int = 3, archived: bool = False) -> ReviewItem:
    item = ReviewItem.objects.create(
        user=user,
        rule="past simple with a finished time expression",
        box=box,
        due_on=TODAY,
        archived_at=timezone.now() if archived else None,
    )
    attempt = Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=3),
    )
    ReviewOccurrence.objects.create(
        item=item, attempt=attempt, produced="I have worked there", correct="I worked there"
    )
    return item


def _answer(item: ReviewItem, step: int, attempt: int, correct: bool) -> ReviewAnswer:
    return ReviewAnswer.objects.create(
        item=item, step=step, attempt=attempt, heard="x", correct=correct, feedback="f"
    )


def _migrate() -> None:
    migration.close_items_stuck_after_step_one(django_apps, None)


def test_an_item_parked_in_step_two_after_missing_step_one_is_closed_as_a_failure(student):
    item = _item(student, box=3)
    first = _answer(item, 1, 1, False)
    second = _answer(item, 1, 2, False)

    _migrate()

    item.refresh_from_db()
    assert (item.box, item.due_on) == (0, TODAY + timedelta(days=1))
    result = item.results.get()
    assert (result.outcome, result.box_before, result.box_after) == (
        ReviewResultKind.FAILED, 3, 0,
    )
    assert result.due_on_after == TODAY + timedelta(days=1)
    for answer in (first, second):
        answer.refresh_from_db()
        assert answer.result_id == result.pk


def test_a_step_two_answer_given_after_the_miss_belongs_to_the_closing_result(student):
    item = _item(student)
    _answer(item, 1, 1, False)
    _answer(item, 1, 2, False)
    step_two = _answer(item, 2, 1, True)

    _migrate()

    step_two.refresh_from_db()
    assert step_two.result_id == item.results.get().pk


def test_an_item_that_hit_step_one_stays_in_step_two(student):
    item = _item(student)
    answer = _answer(item, 1, 1, True)

    _migrate()

    item.refresh_from_db()
    assert (item.box, item.due_on) == (3, TODAY)
    assert not item.results.exists()
    answer.refresh_from_db()
    assert answer.result_id is None


def test_an_item_with_one_miss_waits_for_the_second_attempt(student):
    item = _item(student)
    _answer(item, 1, 1, False)

    _migrate()

    assert not item.results.exists()


def test_an_archived_item_and_an_item_without_open_answers_are_left_alone(student):
    archived = _item(student, archived=True)
    _answer(archived, 1, 1, False)
    _answer(archived, 1, 2, False)
    untouched = _item(student)

    _migrate()

    assert not archived.results.exists()
    assert not untouched.results.exists()


def test_running_it_twice_closes_each_item_once(student):
    item = _item(student)
    _answer(item, 1, 1, False)
    _answer(item, 1, 2, False)

    _migrate()
    _migrate()

    assert item.results.count() == 1
