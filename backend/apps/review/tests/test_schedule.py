from datetime import date

import pytest

from apps.review.services.schedule import (
    BOX_INTERVAL_DAYS,
    FIRST_BOX,
    LAST_BOX,
    ReviewOutcome,
    due_date,
    is_mastered,
    next_box,
    restart,
)

TODAY = date(2026, 10, 7)


def test_the_boxes_are_1_3_7_14_30_then_60_and_120_days():
    assert BOX_INTERVAL_DAYS == (1, 3, 7, 14, 30, 60, 120)


@pytest.mark.parametrize("box", range(len(BOX_INTERVAL_DAYS) - 1))
def test_first_try_moves_up_one_box(box):
    assert next_box(box, ReviewOutcome.FIRST_TRY) == box + 1


def test_first_try_on_the_last_box_stays_there():
    assert next_box(LAST_BOX, ReviewOutcome.FIRST_TRY) == LAST_BOX


@pytest.mark.parametrize("box", range(len(BOX_INTERVAL_DAYS)))
def test_second_try_repeats_the_box(box):
    assert next_box(box, ReviewOutcome.SECOND_TRY) == box


@pytest.mark.parametrize("box", range(len(BOX_INTERVAL_DAYS)))
def test_a_failure_goes_back_to_the_first_box(box):
    assert next_box(box, ReviewOutcome.FAILED) == FIRST_BOX


def test_first_try_on_the_3_day_box_comes_back_in_7_days():
    box = next_box(BOX_INTERVAL_DAYS.index(3), ReviewOutcome.FIRST_TRY)

    assert due_date(box, TODAY) == date(2026, 10, 14)


def test_second_try_on_the_3_day_box_comes_back_in_3_days():
    box = next_box(BOX_INTERVAL_DAYS.index(3), ReviewOutcome.SECOND_TRY)

    assert due_date(box, TODAY) == date(2026, 10, 10)


def test_first_try_on_the_30_day_box_masters_the_item_for_60_days():
    thirty = BOX_INTERVAL_DAYS.index(30)
    box = next_box(thirty, ReviewOutcome.FIRST_TRY)

    assert not is_mastered(thirty)
    assert is_mastered(box)
    assert due_date(box, TODAY) == date(2026, 12, 6)


def test_failing_a_mastered_item_unmasters_it():
    box = next_box(BOX_INTERVAL_DAYS.index(120), ReviewOutcome.FAILED)

    assert not is_mastered(box)
    assert due_date(box, TODAY) == date(2026, 10, 8)


def test_restart_puts_the_item_in_the_first_box_due_tomorrow():
    assert restart(TODAY) == (FIRST_BOX, date(2026, 10, 8))


def test_out_of_range_boxes_are_clamped():
    assert next_box(99, ReviewOutcome.SECOND_TRY) == LAST_BOX
    assert due_date(99, TODAY) == date(2027, 2, 4)
