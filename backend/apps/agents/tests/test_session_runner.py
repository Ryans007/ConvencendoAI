import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import session_runner
from apps.agents.services.evaluator import EvaluationOutcome, JudgedDimension
from apps.catalog.models import Level, Scenario
from apps.progress.models import Attempt, AttemptCriterion, ScoreBreakdown

pytestmark = pytest.mark.django_db


def test_run_and_record_attempt_persists_score_and_criteria(django_user_model, monkeypatch):
    user = django_user_model.objects.create(username="aluno")
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)  # pesos: objective 30, vocabulary 10, pragmatics 15,
    # fluency 15, grammar 15, autonomy 5 — soma 90 (pronuncia fora do modo texto).

    final_state = {
        "messages": [
            AIMessage(content="[Rachel] Hi, what happened with the deadline?"),
            HumanMessage(content="The scope grew and I need one more week."),
        ]
    }
    monkeypatch.setattr(session_runner, "run_graph", lambda content, memory: final_state)

    outcome = EvaluationOutcome(
        confirmed_criteria={"c1", "c2"},
        judged_dimensions=[
            JudgedDimension(dimension="fluency", value=12, weight=15),
            JudgedDimension(dimension="vocabulary", value=8, weight=10),
            JudgedDimension(dimension="grammar", value=12, weight=15),
            JudgedDimension(dimension="pragmatics", value=10, weight=15),
            JudgedDimension(dimension="autonomy", value=4, weight=5),
        ],
        feedback="Good effort explaining the delay.",
        memory_summary="Asked for one extra week on the module.",
        review_items=[],
    )
    monkeypatch.setattr(session_runner, "evaluate", lambda content, messages: outcome)

    attempt = session_runner.run_and_record_attempt(user, scenario, level)

    assert attempt.user == user
    assert attempt.scenario == scenario
    assert attempt.level == level
    assert attempt.completed_at is not None
    assert attempt.memory_summary == outcome.memory_summary
    assert attempt.feedback == outcome.feedback

    breakdowns = {b.dimension: b for b in ScoreBreakdown.objects.filter(attempt=attempt)}
    assert set(breakdowns) == {
        "objective", "fluency", "vocabulary", "grammar", "pragmatics", "autonomy",
    }
    # 2 de 4 critérios cumpridos: metade do peso do objetivo (30 * 0.5 = 15).
    assert breakdowns["objective"].value == 15
    assert breakdowns["objective"].weight_at_time == 30

    achieved = sum(b.value for b in breakdowns.values())
    possible = sum(b.weight_at_time for b in breakdowns.values())
    expected_score = round(achieved / possible * 100)
    assert attempt.final_score == expected_score

    criteria = {c.code: c for c in AttemptCriterion.objects.filter(attempt=attempt)}
    assert set(criteria) == {"c1", "c2", "c3", "c4"}
    assert criteria["c1"].met is True
    assert criteria["c2"].met is True
    assert criteria["c3"].met is False
    assert criteria["c4"].met is False

    assert Attempt.objects.filter(pk=attempt.pk).count() == 1
