import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.review.models import ReviewAnswer, ReviewItem, ReviewResult
from apps.review.models.review_result import ReviewResultKind
from apps.usage.services.student_statistics import student_statistics

pytestmark = pytest.mark.django_db

_PASSWORD = "Xk9#mQ2vLp8Z"
_ROW = re.compile(r"<tr[^>]*>(?:(?!</tr>).)*maria(?:(?!</tr>).)*</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create_user(username="maria", password=_PASSWORD)


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser(
        username="chefe", email="chefe@empresa.com", password=_PASSWORD
    )


def _attempt(user, slug="entrevista-de-emprego", level=1, score=None, passed=None, hints=0):
    attempt = Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug=slug),
        level=Level.objects.get(order=level),
        hints_used=hints,
    )
    if score is not None:
        attempt.final_score = score
        attempt.passed = passed
        attempt.completed_at = timezone.now()
        attempt.save()
    return attempt


def _review(user, *outcomes: str, answers: int = 0) -> ReviewItem:
    item = ReviewItem.objects.create(user=user, rule="regra", box=0, due_on=timezone.localdate())
    for outcome in outcomes:
        ReviewResult.objects.create(item=item, outcome=outcome, box_before=0, box_after=1)
    for number in range(answers):
        ReviewAnswer.objects.create(
            item=item, step=1, attempt=1 + number % 2, heard="x", correct=True, feedback="f"
        )
    return item


def test_a_student_with_completed_and_abandoned_sessions_and_reviews(student):
    _attempt(student, score=80, passed=True, hints=2)
    _attempt(student, level=2, score=40, passed=False, hints=1)
    _attempt(student, slug="negociar-prazo", level=3)
    _review(
        student,
        ReviewResultKind.FIRST_TRY,
        ReviewResultKind.FAILED,
        ReviewResultKind.DISCARDED,
        answers=3,
    )

    stats = student_statistics(student)

    assert stats.sessions_started == 3
    assert stats.sessions_completed == 2
    assert stats.sessions_abandoned == 1
    assert stats.scenarios_practiced == 2
    assert stats.levels_practiced == 3
    assert stats.average_score == 60
    assert stats.approvals == 1
    assert stats.hints_used == 3
    assert stats.review_answers == 3
    assert stats.review_items_reviewed == 2
    assert stats.review_hits == 1
    assert stats.last_activity is not None


def test_a_student_who_never_practiced_has_zeros_and_no_average(student):
    stats = student_statistics(student)

    assert stats.sessions_started == 0
    assert stats.average_score is None
    assert stats.hints_used == 0
    assert stats.last_activity is None


def test_the_statistics_of_a_student_never_include_another_students_data(
    student, django_user_model
):
    other = django_user_model.objects.create_user(username="joao", password=_PASSWORD)
    _attempt(other, score=90, passed=True)
    _review(other, ReviewResultKind.FIRST_TRY, answers=2)

    stats = student_statistics(student)

    assert stats.sessions_started == 0
    assert stats.review_answers == 0
    assert stats.review_items_reviewed == 0


def test_the_last_activity_is_the_most_recent_of_sessions_and_review(student):
    old = _attempt(student, score=50, passed=False)
    Attempt.objects.filter(pk=old.pk).update(started_at=timezone.now() - timedelta(days=10))
    item = _review(student, answers=1)

    assert student_statistics(student).last_activity == item.answers.get().created_at


def test_the_superuser_sees_the_usage_columns_in_the_user_list(client, superuser, student):
    _attempt(student, score=80, passed=True)
    _attempt(student, level=2)
    client.force_login(superuser)

    page = client.get(reverse("admin:users_user_changelist")).content.decode()

    row = _ROW.search(page).group(0)
    cells = [cell.strip() for cell in _CELL.findall(row)]
    assert cells[-6:] == ["2", "1", "1", "80", "0", "0.0000"]


def test_the_user_detail_shows_the_statistics_section_to_the_superuser(
    client, superuser, student
):
    _attempt(student, score=70, passed=True)
    client.force_login(superuser)

    page = client.get(reverse("admin:users_user_change", args=[student.pk])).content.decode()

    assert "Estatísticas de uso" in page
    assert "Sessões concluídas" in page
    assert "Sessões abandonadas" in page


def test_a_staff_user_who_is_not_superuser_sees_no_usage_at_all(
    client, django_user_model, student
):
    staff = django_user_model.objects.create_user(
        username="equipe", password=_PASSWORD, is_staff=True
    )
    staff.user_permissions.set(Permission.objects.filter(content_type__app_label="users"))
    client.force_login(staff)

    listing = client.get(reverse("admin:users_user_changelist")).content.decode()
    detail = client.get(reverse("admin:users_user_change", args=[student.pk])).content.decode()

    assert "Concluídas" not in listing
    assert "Nota média" not in listing
    assert "Estatísticas de uso" not in detail


def test_the_list_does_not_query_once_per_user(client, superuser, django_user_model):
    def count_queries() -> int:
        client.force_login(superuser)
        with CaptureQueriesContext(connection) as queries:
            client.get(reverse("admin:users_user_changelist"))
        return len(queries)

    for number in range(2):
        user = django_user_model.objects.create_user(username=f"a{number}", password=_PASSWORD)
        _attempt(user, score=60, passed=True)
    baseline = count_queries()
    for number in range(2, 8):
        user = django_user_model.objects.create_user(username=f"a{number}", password=_PASSWORD)
        _attempt(user, score=60, passed=True)

    assert count_queries() == baseline
