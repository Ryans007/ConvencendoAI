from dataclasses import dataclass

import pytest

from apps.review.services.item_progress import (
    ItemProgress,
    item_outcome,
    item_progress,
    revealed_correct,
)
from apps.review.services.schedule import ReviewOutcome


@dataclass
class Answer:
    step: int
    attempt: int
    correct: bool


def _answers(*pairs: tuple[int, int, bool]) -> list[Answer]:
    return [Answer(*pair) for pair in pairs]


def test_an_item_with_no_answers_starts_at_step_one_attempt_one():
    assert item_progress([]) == ItemProgress(step=1, attempt=1, finished=False)


def test_a_correct_first_attempt_ends_step_one_and_moves_to_step_two():
    progress = item_progress(_answers((1, 1, True)))

    assert progress == ItemProgress(step=2, attempt=1, finished=False)


def test_a_wrong_first_attempt_stays_in_the_step_for_a_second_attempt():
    progress = item_progress(_answers((1, 1, False)))

    assert progress == ItemProgress(step=1, attempt=2, finished=False)


def test_two_wrong_attempts_end_the_review_without_step_two():
    progress = item_progress(_answers((1, 1, False), (1, 2, False)))

    assert progress == ItemProgress(step=1, attempt=2, finished=True)


def test_a_correct_second_attempt_ends_the_step():
    progress = item_progress(_answers((1, 1, False), (1, 2, True)))

    assert progress == ItemProgress(step=2, attempt=1, finished=False)


def test_step_two_first_attempt_wrong_asks_for_the_second():
    progress = item_progress(_answers((1, 1, True), (2, 1, False)))

    assert progress == ItemProgress(step=2, attempt=2, finished=False)


@pytest.mark.parametrize(
    "answers",
    [
        ((1, 1, True), (2, 1, True)),
        ((1, 1, True), (2, 1, False), (2, 2, True)),
        ((1, 1, True), (2, 1, False), (2, 2, False)),
        ((1, 1, False), (1, 2, False)),
        ((1, 1, False), (1, 2, True), (2, 1, True)),
    ],
)
def test_the_item_is_finished_when_the_review_ends(answers):
    assert item_progress(_answers(*answers)).finished is True


def test_the_finished_progress_describes_the_last_step_two_answer():
    progress = item_progress(_answers((1, 1, True), (2, 1, False), (2, 2, True)))

    assert progress == ItemProgress(step=2, attempt=2, finished=True)


def test_both_steps_right_on_the_first_try_is_a_first_try_outcome():
    assert item_outcome(_answers((1, 1, True), (2, 1, True))) is ReviewOutcome.FIRST_TRY


def test_a_second_attempt_in_step_one_is_a_second_try_outcome():
    answers = _answers((1, 1, False), (1, 2, True), (2, 1, True))

    assert item_outcome(answers) is ReviewOutcome.SECOND_TRY


def test_a_second_attempt_in_step_two_is_a_second_try_outcome():
    answers = _answers((1, 1, True), (2, 1, False), (2, 2, True))

    assert item_outcome(answers) is ReviewOutcome.SECOND_TRY


def test_step_one_without_a_correct_answer_is_a_failure():
    answers = _answers((1, 1, False), (1, 2, False))

    assert item_outcome(answers) is ReviewOutcome.FAILED


def test_step_two_without_a_correct_answer_is_a_failure():
    answers = _answers((1, 1, True), (2, 1, False), (2, 2, False))

    assert item_outcome(answers) is ReviewOutcome.FAILED


def _reveal(step: int, attempt: int, correct: bool) -> str:
    return revealed_correct(
        step=step,
        attempt=attempt,
        correct=correct,
        item_correct="I worked there yesterday.",
        correction="Last week I finished the project.",
    )


def test_a_first_wrong_attempt_reveals_nothing():
    assert _reveal(1, 1, False) == ""
    assert _reveal(2, 1, False) == ""


def test_the_end_of_step_one_reveals_the_item_correct_form_right_or_wrong():
    assert _reveal(1, 1, True) == "I worked there yesterday."
    assert _reveal(1, 2, True) == "I worked there yesterday."
    assert _reveal(1, 2, False) == "I worked there yesterday."


def test_step_two_ending_without_a_hit_reveals_the_teacher_correction():
    assert _reveal(2, 2, False) == "Last week I finished the project."


def test_step_two_ending_with_a_hit_reveals_nothing():
    assert _reveal(2, 1, True) == ""
    assert _reveal(2, 2, True) == ""
