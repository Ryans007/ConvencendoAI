from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.review.models import ReviewItem
from apps.review.services.reset_due import make_items_due

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="aluno", password="Xk9#mQ2vLp8Z")


def _item(user, *, rule: str, box: int = 2, days_ahead: int = 7, archived: bool = False):
    return ReviewItem.objects.create(
        user=user,
        rule=rule,
        box=box,
        due_on=TODAY + timedelta(days=days_ahead),
        archived_at=timezone.now() if archived else None,
    )


def test_every_active_item_becomes_due_today_and_keeps_its_box(student):
    future = _item(student, rule="a", box=3, days_ahead=14)
    late = _item(student, rule="b", box=1, days_ahead=-2)

    changed = make_items_due(student, TODAY)

    assert changed == 2
    future.refresh_from_db()
    late.refresh_from_db()
    assert future.due_on == TODAY and future.box == 3
    assert late.due_on == TODAY and late.box == 1


def test_restarting_the_boxes_sends_the_items_back_to_the_first_one(student):
    item = _item(student, rule="a", box=5)

    make_items_due(student, TODAY, restart_boxes=True)

    item.refresh_from_db()
    assert item.due_on == TODAY and item.box == 0


def test_an_archived_item_is_left_alone(student):
    archived = _item(student, rule="a", archived=True)

    changed = make_items_due(student, TODAY, restart_boxes=True)

    assert changed == 0
    archived.refresh_from_db()
    assert archived.due_on == TODAY + timedelta(days=7) and archived.box == 2


def test_another_students_items_are_left_alone(student, django_user_model):
    other = django_user_model.objects.create_user(username="outro", password="Xk9#mQ2vLp8Z")
    theirs = _item(other, rule="a")

    make_items_due(student, TODAY)

    theirs.refresh_from_db()
    assert theirs.due_on == TODAY + timedelta(days=7)


def test_the_command_reports_how_many_items_changed(student):
    item = _item(student, rule="a")
    out = StringIO()

    call_command("reset_review_due", user="aluno", stdout=out)

    item.refresh_from_db()
    assert item.due_on == TODAY
    assert "1 item(ns)" in out.getvalue()


def test_the_command_can_restart_the_boxes(student):
    item = _item(student, rule="a", box=4)

    call_command("reset_review_due", user="aluno", restart_boxes=True, stdout=StringIO())

    item.refresh_from_db()
    assert item.box == 0


def test_the_command_rejects_an_unknown_user():
    with pytest.raises(CommandError):
        call_command("reset_review_due", user="ninguem", stdout=StringIO())
