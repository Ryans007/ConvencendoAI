import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import evaluator
from apps.agents.services.schemas import EvaluationResult, ReviewItem
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _FakeStructuredLLM:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        return self._result


def _content():
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    return load_scenario_content(scenario, level)


def test_evaluate_clamps_scores_and_filters_invalid_criteria(monkeypatch):
    content = _content()
    fake_result = EvaluationResult(
        confirmed_criteria=["c1", "c2", "not-a-real-criterion"],
        sub_scores={
            "fluency": 999,
            "vocabulary": -5,
            "grammar": 10,
            "pragmatics": 3.6,
            "autonomy": 100,
            "pronunciation": 50,
        },
        feedback=" Great job overall. ",
        memory_summary=" Works as a backend developer. ",
        review_items=[ReviewItem(item="preposition", produced="interest in", correct="interested in")],
    )
    monkeypatch.setattr(
        evaluator, "get_structured_llm", lambda purpose, schema: _FakeStructuredLLM(fake_result)
    )

    messages = [
        AIMessage(content="[Rachel] Hi, tell me about the delay."),
        HumanMessage(content="The scope grew after we agreed the deadline."),
    ]
    outcome = evaluator.evaluate(content, messages)

    assert outcome.confirmed_criteria == {"c1", "c2"}
    assert outcome.feedback == "Great job overall."
    assert outcome.memory_summary == "Works as a backend developer."
    assert len(outcome.review_items) == 1

    by_dimension = {d.dimension: d for d in outcome.judged_dimensions}
    assert set(by_dimension) == {"fluency", "vocabulary", "grammar", "pragmatics", "autonomy"}
    assert by_dimension["fluency"].value == 15  # clamped to the weight ceiling
    assert by_dimension["vocabulary"].value == 0  # clamped to the floor
    assert by_dimension["grammar"].value == 10
    assert by_dimension["pragmatics"].value == 4  # rounded
    assert by_dimension["autonomy"].value == 5  # clamped to the weight ceiling


def test_evaluate_never_judges_objective_or_pronunciation(monkeypatch):
    content = _content()
    fake_result = EvaluationResult(confirmed_criteria=[], sub_scores={})
    monkeypatch.setattr(
        evaluator, "get_structured_llm", lambda purpose, schema: _FakeStructuredLLM(fake_result)
    )

    outcome = evaluator.evaluate(content, [])

    dimensions = {d.dimension for d in outcome.judged_dimensions}
    assert "objective" not in dimensions
    assert "pronunciation" not in dimensions


def _captured_evaluation_prompt(monkeypatch, level_order: int) -> str:
    scenario = Scenario.objects.get(slug="entrevista-de-emprego")
    content = load_scenario_content(scenario, Level.objects.get(order=level_order))
    prompts = []

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return EvaluationResult()

    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: _RecordingLLM())
    evaluator.evaluate(
        content,
        [AIMessage(content="[Rachel] Did you work in a team?"), HumanMessage(content="Yes, I did.")],
    )
    return prompts[0]


def test_evaluation_prompt_carries_the_level_answer_format(monkeypatch):
    content_level_1 = Level.objects.get(order=1)

    prompt = _captured_evaluation_prompt(monkeypatch, 1)

    assert content_level_1.expected_production in prompt
    assert "WHAT THIS LEVEL ASKS OF THE STUDENT" in prompt


def test_evaluation_prompt_forbids_penalising_the_format_the_level_asks_for(monkeypatch):
    prompt = _captured_evaluation_prompt(monkeypatch, 1)

    assert "it is NOT a weakness" in prompt
    assert "never mention its brevity as something to improve" in prompt
    assert "Never present as" in prompt


def test_evaluation_prompt_changes_with_the_level(monkeypatch):
    level_1 = _captured_evaluation_prompt(monkeypatch, 1)
    level_3 = _captured_evaluation_prompt(monkeypatch, 3)

    assert Level.objects.get(order=3).expected_production in level_3
    assert Level.objects.get(order=3).expected_production not in level_1
