import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import session_runner
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt, ScoreBreakdown, SpeechTurn

pytestmark = pytest.mark.django_db

_STATE = {
    "messages": [
        AIMessage(content="[Rachel] What happened with the deadline?"),
        HumanMessage(content="The scope grew and I need one more week."),
    ]
}


def _outcome() -> EvaluationOutcome:
    return EvaluationOutcome(
        confirmed_criteria=set(),
        judged_dimensions=[
            JudgedDimension(dimension="fluency", value=10, weight=15, comment="Fluência ok."),
            JudgedDimension(dimension="vocabulary", value=8, weight=10),
            JudgedDimension(dimension="grammar", value=9, weight=15, comment="Gramática ok."),
            JudgedDimension(dimension="pragmatics", value=10, weight=15),
            JudgedDimension(dimension="autonomy", value=4, weight=5),
        ],
        feedback="Você explicou bem o atraso.",
        memory_summary="Asked for one extra week.",
        review_items=[],
    )


def _turn(**overrides) -> dict:
    turn = {
        "waited_ms": 3500,
        "leading_silence_ms": 500,
        "speech_ms": 20000,
        "word_count": 30,
        "long_pauses": 1,
        "after_hint": False,
        "text": "The scope grew and I need one more week.",
    }
    turn.update(overrides)
    return turn


def _record(user, monkeypatch, *turns: dict):
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    attempt = Attempt.objects.create(user=user, scenario=scenario, level=level)
    for order, turn in enumerate(turns, start=1):
        SpeechTurn.objects.create(attempt=attempt, order=order, **turn)
    received = []

    def fake_evaluate(content, messages, known_rules=(), speech_metrics=None):
        received.append(speech_metrics)
        return _outcome()

    monkeypatch.setattr(session_runner, "evaluate", fake_evaluate)
    session_runner.evaluate_and_record_attempt(
        attempt, load_scenario_content(scenario, level), _STATE
    )
    breakdowns = {b.dimension: b for b in ScoreBreakdown.objects.filter(attempt=attempt)}
    return breakdowns, received[0]


def test_a_voice_session_combines_measured_fluency_with_the_judged_score(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="aluno")

    breakdowns, metrics = _record(user, monkeypatch, _turn(), _turn())

    assert metrics.reaction_seconds == 4.0
    assert metrics.words_per_minute == 90
    measured = 0.4 * (8.0 - 4.0) / 5.5 + 0.4 * (90 - 40) / 60 + 0.2 * (10 - 100 / 30) / 8
    assert breakdowns["fluency"].value == round(15 * (0.7 * measured + 0.3 * 10 / 15))


def test_comments_are_recorded_with_each_sub_score(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")

    breakdowns, _ = _record(user, monkeypatch, _turn())

    assert breakdowns["fluency"].comment == "Fluência ok."
    assert breakdowns["grammar"].comment == "Gramática ok."
    assert breakdowns["objective"].comment == ""


def test_without_speech_turns_fluency_and_vocabulary_are_the_judged_scores(
    django_user_model, monkeypatch
):
    user = django_user_model.objects.create(username="aluno")

    breakdowns, metrics = _record(user, monkeypatch)

    assert metrics is None
    assert breakdowns["fluency"].value == 10
    assert breakdowns["vocabulary"].value == 8


def test_a_short_voice_session_keeps_vocabulary_judged(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")

    breakdowns, metrics = _record(user, monkeypatch, _turn())

    assert metrics.lexical_diversity is None
    assert breakdowns["vocabulary"].value == 8
