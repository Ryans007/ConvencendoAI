import pytest

from apps.progress.services.speech_metrics import SessionSpeechMetrics
from apps.progress.services.speech_scoring import (
    fluency_score,
    measured_fluency,
    vocabulary_score,
)
from apps.progress.speech_bands import Band, rules_for_level


def _metrics(
    *,
    reaction=None,
    speed=None,
    pauses=None,
    diversity=None,
    lexical_range=None,
    word_count=100,
) -> SessionSpeechMetrics:
    return SessionSpeechMetrics(
        reaction_seconds=reaction,
        words_per_minute=speed,
        long_pauses_per_100_words=pauses,
        lexical_diversity=diversity,
        lexical_range=lexical_range,
        word_count=word_count,
    )


def test_a_band_is_full_at_its_limit_zero_at_the_other_and_linear_between():
    band = Band(full=2.5, zero=8.0)

    assert band.fraction(2.0) == 1.0
    assert band.fraction(9.0) == 0.0
    assert band.fraction(4.0) == pytest.approx(0.73, abs=0.01)


def test_a_band_where_more_is_better():
    assert Band(full=80.0, zero=40.0).fraction(120.0) == 1.0
    assert Band(full=80.0, zero=40.0).fraction(60.0) == 0.5


def test_level_three_fluency_with_every_measure():
    metrics = _metrics(reaction=4.0, speed=90.0, pauses=3.0)

    assert measured_fluency(metrics, rules_for_level(3)) == pytest.approx(0.80, abs=0.01)
    assert fluency_score(15, 10, metrics, rules_for_level(3)) == 11


def test_level_one_fluency_uses_only_the_reaction():
    metrics = _metrics(reaction=4.0, speed=10.0, pauses=50.0)

    assert measured_fluency(metrics, rules_for_level(1)) == 1.0


def test_without_reaction_fluency_is_the_judged_score():
    assert fluency_score(15, 9, _metrics(speed=90.0, pauses=3.0), rules_for_level(3)) == 9
    assert fluency_score(15, 9, None, rules_for_level(3)) == 9


def test_a_missing_measure_does_not_count_as_zero():
    metrics = _metrics(reaction=2.0, speed=None, pauses=None)

    assert measured_fluency(metrics, rules_for_level(3)) == 1.0


def test_level_three_vocabulary_with_its_three_parts():
    metrics = _metrics(diversity=0.60, lexical_range=0.05)

    assert vocabulary_score(15, 12, metrics, rules_for_level(3)) == 10


def test_level_one_vocabulary_is_only_the_judged_score():
    metrics = _metrics(diversity=0.45, lexical_range=0.0)

    assert vocabulary_score(5, 4, metrics, rules_for_level(1)) == 4


def test_level_two_vocabulary_ignores_range():
    metrics = _metrics(diversity=0.70, lexical_range=0.0)

    assert vocabulary_score(10, 7, metrics, rules_for_level(2)) == round(10 * (0.7 * 0.7 + 0.3))


def test_vocabulary_without_diversity_is_the_judged_score():
    assert vocabulary_score(15, 11, _metrics(word_count=40), rules_for_level(3)) == 11


def test_scores_never_pass_the_weight():
    metrics = _metrics(reaction=0.5, speed=200.0, pauses=0.0, diversity=1.0, lexical_range=1.0)

    assert fluency_score(15, 20, metrics, rules_for_level(3)) == 15
    assert vocabulary_score(15, 20, metrics, rules_for_level(3)) == 15


def test_an_unknown_level_uses_the_closest_level_below():
    assert rules_for_level(5) == rules_for_level(3)
    assert rules_for_level(0) == rules_for_level(1)
