from datetime import date, timedelta

import pytest
from django.utils import timezone
from langchain_core.messages import HumanMessage

from apps.agents.services import session_runner
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.schemas import ReviewItem as ReportedMistake
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt
from apps.review.models import ReviewItem, ReviewOccurrence
from apps.review.services.recording import (
    known_rule_id,
    known_rules_for,
    record_review_items,
)

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 7)
PAST_SIMPLE = "past simple with a finished time expression"


def _attempt(user) -> Attempt:
    return Attempt.objects.create(
        user=user,
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=3),
    )


def _mistake(rule, produced, correct, repeats="", note="") -> ReportedMistake:
    return ReportedMistake(
        rule=rule, produced=produced, correct=correct, repeats=repeats, note=note
    )


@pytest.fixture
def student(django_user_model):
    return django_user_model.objects.create(username="aluno")


def test_a_new_rule_becomes_an_item_due_tomorrow_with_its_occurrence(student):
    attempt = _attempt(student)

    record_review_items(
        student,
        attempt,
        [_mistake(PAST_SIMPLE, "I have worked there yesterday", "I worked there yesterday")],
        TODAY,
    )

    item = ReviewItem.objects.get(user=student)
    assert (item.rule, item.box, item.due_on) == (PAST_SIMPLE, 0, date(2026, 10, 8))
    occurrence = item.occurrences.get()
    assert occurrence.attempt == attempt
    assert occurrence.produced == "I have worked there yesterday"
    assert occurrence.correct == "I worked there yesterday"


def test_a_repeated_rule_adds_an_occurrence_and_restarts_even_a_mastered_item(student):
    item = ReviewItem.objects.create(user=student, rule=PAST_SIMPLE, box=6, due_on=date(2027, 1, 1))
    attempt = _attempt(student)

    record_review_items(
        student,
        attempt,
        [
            _mistake(
                "past simple with finished time",
                "I have finished the API last week",
                "I finished the API last week",
                repeats=known_rule_id(item),
            )
        ],
        TODAY,
    )

    assert ReviewItem.objects.filter(user=student).count() == 1
    item.refresh_from_db()
    assert (item.box, item.due_on) == (0, date(2026, 10, 8))
    assert item.occurrences.first().produced == "I have finished the API last week"


def test_another_rule_becomes_another_item(student):
    ReviewItem.objects.create(user=student, rule=PAST_SIMPLE, box=2, due_on=date(2026, 10, 20))

    record_review_items(
        student,
        _attempt(student),
        [_mistake("third person -s: doesn't", "She don't like it", "She doesn't like it")],
        TODAY,
    )

    assert ReviewItem.objects.filter(user=student).count() == 2


def test_the_same_new_rule_twice_in_a_session_is_one_item(student):
    record_review_items(
        student,
        _attempt(student),
        [
            _mistake(PAST_SIMPLE, "I have worked there yesterday", "I worked there yesterday"),
            _mistake(
                "Past simple with a  finished time expression",
                "I have seen him last year",
                "I saw him last year",
            ),
        ],
        TODAY,
    )

    item = ReviewItem.objects.get(user=student)
    assert item.occurrences.count() == 2


def test_at_most_four_occurrences_per_session(student):
    mistakes = [_mistake(f"rule {n}", f"wrong {n}", f"right {n}") for n in range(6)]

    record_review_items(student, _attempt(student), mistakes, TODAY)

    assert ReviewOccurrence.objects.filter(item__user=student).count() == 4


def test_a_session_without_mistakes_changes_nothing(student):
    item = ReviewItem.objects.create(user=student, rule=PAST_SIMPLE, box=3, due_on=date(2026, 10, 20))

    record_review_items(student, _attempt(student), [], TODAY)

    item.refresh_from_db()
    assert (item.box, item.due_on) == (3, date(2026, 10, 20))
    assert ReviewOccurrence.objects.count() == 0


def test_known_rules_include_mastered_items_and_only_the_students_own(student, django_user_model):
    mine = ReviewItem.objects.create(user=student, rule=PAST_SIMPLE, box=6, due_on=TODAY)
    other = django_user_model.objects.create(username="outro")
    ReviewItem.objects.create(user=other, rule="articles", box=0, due_on=TODAY)

    known = known_rules_for(student)

    assert [(rule.id, rule.rule) for rule in known] == [(known_rule_id(mine), PAST_SIMPLE)]


def _outcome(review_items) -> EvaluationOutcome:
    return EvaluationOutcome(
        confirmed_criteria=set(),
        judged_dimensions=[JudgedDimension(dimension="fluency", value=10, weight=15)],
        feedback="Ok.",
        memory_summary="Trabalha com backend.",
        review_items=review_items,
    )


def test_recording_an_attempt_passes_the_known_rules_and_records_the_items(
    student, monkeypatch
):
    item = ReviewItem.objects.create(user=student, rule=PAST_SIMPLE, box=4, due_on=TODAY)
    content, _memory, attempt = session_runner.resolve_execution(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3), student
    )
    received = []

    def fake_evaluate(content, messages, known_rules=()):
        received.append(list(known_rules))
        return _outcome(
            [
                _mistake(PAST_SIMPLE, "I have went", "I went", repeats=known_rule_id(item)),
                _mistake("articles before jobs", "I am developer", "I am a developer"),
            ]
        )

    monkeypatch.setattr(session_runner, "evaluate", fake_evaluate)

    session_runner.evaluate_and_record_attempt(
        attempt, content, {"messages": [HumanMessage(content="I am developer.")]}
    )

    assert [rule.id for rule in received[0]] == [known_rule_id(item)]
    item.refresh_from_db()
    session_day = timezone.localdate(Attempt.objects.get(pk=attempt.pk).completed_at)
    assert item.box == 0
    assert item.due_on == session_day + timedelta(days=1)
    assert ReviewItem.objects.filter(user=student).count() == 2
    assert ReviewOccurrence.objects.filter(attempt=attempt).count() == 2


def test_a_failure_while_recording_the_items_undoes_the_attempt(student, monkeypatch):
    content, _memory, attempt = session_runner.resolve_execution(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3), student
    )
    monkeypatch.setattr(
        session_runner, "evaluate", lambda content, messages, known_rules=(): _outcome([])
    )

    def broken_recording(*args):
        raise RuntimeError("falha ao gravar")

    monkeypatch.setattr(session_runner, "record_review_items", broken_recording)

    with pytest.raises(RuntimeError):
        session_runner.evaluate_and_record_attempt(
            attempt, content, {"messages": [HumanMessage(content="Hi.")]}
        )

    saved = Attempt.objects.get(pk=attempt.pk)
    assert saved.completed_at is None
    assert saved.score_breakdowns.count() == 0


def test_a_repeated_rule_brings_an_archived_item_back(student):
    item = ReviewItem.objects.create(
        user=student,
        rule=PAST_SIMPLE,
        box=2,
        due_on=date(2026, 10, 20),
        archived_at=timezone.now(),
    )
    attempt = _attempt(student)

    record_review_items(
        student,
        attempt,
        [
            _mistake(
                PAST_SIMPLE,
                "I have finished the API last week",
                "I finished the API last week",
                repeats=known_rule_id(item),
            )
        ],
        TODAY,
    )

    item.refresh_from_db()
    assert item.archived_at is None
    assert (item.box, item.due_on) == (0, date(2026, 10, 8))
    assert item.occurrences.count() == 1


def test_the_evaluator_still_receives_the_archived_rules(student):
    ReviewItem.objects.create(
        user=student, rule=PAST_SIMPLE, box=0, due_on=TODAY, archived_at=timezone.now()
    )

    assert [known.rule for known in known_rules_for(student)] == [PAST_SIMPLE]


def test_the_occurrence_keeps_the_whole_sentence_and_the_portuguese_note(student):
    attempt = _attempt(student)

    record_review_items(
        student,
        attempt,
        [
            _mistake(
                "verb choice",
                "I want to report it today, please",
                "I want to repair it today, please",
                note="Aqui o verbo é o de consertar, e não o de relatar.",
            )
        ],
        TODAY,
    )

    occurrence = ReviewOccurrence.objects.get(item__user=student)
    assert occurrence.produced == "I want to report it today, please"
    assert occurrence.correct == "I want to repair it today, please"
    assert occurrence.note == "Aqui o verbo é o de consertar, e não o de relatar."


def test_a_mistake_without_a_note_is_recorded_with_an_empty_note(student):
    record_review_items(
        student,
        _attempt(student),
        [_mistake(PAST_SIMPLE, "I have worked there yesterday", "I worked there yesterday")],
        TODAY,
    )

    assert ReviewOccurrence.objects.get(item__user=student).note == ""


def test_the_newest_occurrence_brings_its_own_note(student):
    item = ReviewItem.objects.create(user=student, rule=PAST_SIMPLE, box=3, due_on=TODAY)
    first = _attempt(student)
    record_review_items(
        student,
        first,
        [_mistake("x", "old", "older", repeats=known_rule_id(item), note="Nota antiga.")],
        TODAY,
    )
    record_review_items(
        student,
        _attempt(student),
        [_mistake("x", "new", "newer", repeats=known_rule_id(item), note="Nota nova.")],
        TODAY,
    )

    assert item.occurrences.first().note == "Nota nova."
