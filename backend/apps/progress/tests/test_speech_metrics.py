from dataclasses import dataclass

import pytest

from apps.progress.models import SpeechTurn
from apps.progress.services.speech_metrics import (
    lexical_range,
    measure_turn,
    moving_average_type_token_ratio,
    session_metrics,
)


@dataclass(frozen=True)
class _Word:
    start: float
    end: float


def _turn(
    *,
    waited_ms: int | None = 1000,
    leading_silence_ms: int = 0,
    speech_ms: int = 6000,
    word_count: int = 10,
    long_pauses: int = 0,
    after_hint: bool = False,
    text: str = "",
) -> SpeechTurn:
    return SpeechTurn(
        waited_ms=waited_ms,
        leading_silence_ms=leading_silence_ms,
        speech_ms=speech_ms,
        word_count=word_count,
        long_pauses=long_pauses,
        after_hint=after_hint,
        text=text,
    )


def test_a_turn_measures_the_silence_before_the_first_word_and_the_speech_time():
    measure = measure_turn([_Word(1.5, 1.8), _Word(1.8, 2.1), _Word(2.1, 2.6)])

    assert measure.leading_silence_ms == 1500
    assert measure.speech_ms == 1100
    assert measure.word_count == 3
    assert measure.long_pauses == 0


def test_a_gap_longer_than_one_and_a_half_seconds_is_a_long_pause():
    measure = measure_turn([_Word(0.0, 0.3), _Word(2.3, 2.6), _Word(3.0, 3.2), _Word(4.0, 4.3)])

    assert measure.long_pauses == 1


def test_a_turn_without_words_has_no_measure():
    assert measure_turn([]) is None


def test_the_reaction_adds_the_wait_and_the_leading_silence():
    metrics = session_metrics([_turn(waited_ms=2000, leading_silence_ms=1500)])

    assert metrics.reaction_seconds == 3.5


def test_turns_after_a_hint_stay_out_of_the_reaction_median():
    turns = [_turn(waited_ms=2000) for _ in range(3)] + [_turn(waited_ms=15000, after_hint=True)]

    assert session_metrics(turns).reaction_seconds == 2.0


def test_the_reaction_is_the_median_so_one_distraction_does_not_decide_it():
    turns = [_turn(waited_ms=2000), _turn(waited_ms=3000), _turn(waited_ms=30000)]

    assert session_metrics(turns).reaction_seconds == 3.0


def test_turns_with_an_unknown_wait_stay_out_of_the_reaction():
    metrics = session_metrics([_turn(waited_ms=None), _turn(waited_ms=3000)])

    assert metrics.reaction_seconds == 3.0


def test_without_any_known_wait_there_is_no_reaction():
    assert session_metrics([_turn(waited_ms=None)]).reaction_seconds is None


def test_speed_and_pauses_add_up_every_turn():
    metrics = session_metrics(
        [
            _turn(speech_ms=30000, word_count=40, long_pauses=1),
            _turn(speech_ms=30000, word_count=50, long_pauses=2),
        ]
    )

    assert metrics.words_per_minute == 90
    assert metrics.long_pauses_per_100_words == pytest.approx(3.33, abs=0.01)


def test_a_session_without_turns_has_no_metrics():
    assert session_metrics([]) is None


def test_fewer_than_fifty_words_leave_vocabulary_unmeasured():
    metrics = session_metrics([_turn(text=" ".join(["word"] * 40))])

    assert metrics.word_count == 40
    assert metrics.lexical_diversity is None
    assert metrics.lexical_range is None


def test_vocabulary_is_measured_with_enough_words():
    text = "I would like to book a quiet room for two nights next week, please. " * 5

    metrics = session_metrics([_turn(text=text)])

    assert metrics.word_count == 70
    assert 0 < metrics.lexical_diversity <= 1
    assert 0 <= metrics.lexical_range <= 1


def test_mattr_does_not_drop_just_because_the_speech_is_longer():
    sample = "we need the report by friday and the client wants a short summary first".split()

    once = moving_average_type_token_ratio(sample * 2)
    many = moving_average_type_token_ratio(sample * 8)

    assert once == pytest.approx(many, abs=0.05)


def test_mattr_of_a_text_shorter_than_the_window_is_the_plain_ratio():
    assert moving_average_type_token_ratio(["yes", "yes", "no", "no"]) == 0.5


def test_range_counts_content_words_outside_the_most_common_ones():
    tokens = ["i", "need", "a", "refund", "for", "the", "room"]

    assert lexical_range(tokens) == pytest.approx(1 / 3)


def test_persona_names_and_proper_nouns_never_count_as_vocabulary():
    text = "Emma, I'm sorry. I booked it with Lisbon Travel. " * 8

    metrics = session_metrics([_turn(text=text)], excluded_names=["Emma"])

    assert metrics.word_count == 8 * 6
