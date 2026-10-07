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
        review_items=[
            ReviewItem(
                rule="adjective + preposition", produced="interest in", correct="interested in"
            )
        ],
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


def _prompt_for(monkeypatch, messages) -> str:
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    prompts = []

    class _RecordingLLM:
        def invoke(self, received):
            prompts.append(received[0].content)
            return EvaluationResult()

    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: _RecordingLLM())
    evaluator.evaluate(content, messages)
    return prompts[0]


def test_answers_after_a_hint_are_marked_and_explained_only_for_autonomy(monkeypatch):
    prompt = _prompt_for(
        monkeypatch,
        [
            AIMessage(content="[Tom] What decision did you make?"),
            HumanMessage(content="I chose PostgreSQL.", additional_kwargs={"after_hint": True}),
            AIMessage(content="[Rachel] Did you work in a team?"),
            HumanMessage(content="Yes, four of us."),
        ],
    )

    assert "Student (after a suggested answer): I chose PostgreSQL." in prompt
    assert "Student: Yes, four of us." in prompt
    assert "SUGGESTED ANSWERS" in prompt
    assert "less autonomous in the autonomy score" in prompt
    assert "Judge every other dimension, and the acceptance criteria, exactly as" in prompt


def test_without_hints_the_prompt_has_no_hint_section(monkeypatch):
    prompt = _prompt_for(
        monkeypatch,
        [AIMessage(content="[Tom] What decision did you make?"), HumanMessage(content="Postgres.")],
    )

    assert "SUGGESTED ANSWERS" not in prompt
    assert "after a suggested answer" not in prompt


_SESSION = [
    AIMessage(content="[Tom] When did you finish it?"),
    HumanMessage(content="I have finished it last week."),
]


def _evaluate_with(monkeypatch, review_items, known_rules=()):
    prompts = []

    class _RecordingLLM:
        def invoke(self, received):
            prompts.append(received[0].content)
            return EvaluationResult(review_items=review_items)

    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: _RecordingLLM())
    outcome = evaluator.evaluate(_content(), _SESSION, known_rules)
    return outcome, prompts[0]


def test_the_prompt_lists_the_known_rules_with_their_ids(monkeypatch):
    known = [evaluator.KnownRule(id="r7", rule="past simple with a finished time expression")]

    _, prompt = _evaluate_with(monkeypatch, [], known)

    assert "KNOWN MISTAKES OF THIS STUDENT" in prompt
    assert "- r7: past simple with a finished time expression" in prompt


def test_without_known_rules_the_prompt_says_none_yet(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])

    assert "(none yet)" in prompt


def test_the_prompt_asks_for_rules_of_words_or_structure_and_never_sounds(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])

    assert "about WORDS or\n  STRUCTURE only" in prompt
    assert "Never pronunciation or sounds" in prompt
    assert "the SAME\n    rule, even with different words" in prompt


def test_a_repeat_of_a_known_rule_is_kept(monkeypatch):
    known = [evaluator.KnownRule(id="r7", rule="past simple with a finished time expression")]
    item = ReviewItem(
        rule="past simple with finished time",
        produced="I have finished it last week",
        correct="I finished it last week",
        repeats="r7",
    )

    outcome, _ = _evaluate_with(monkeypatch, [item], known)

    assert outcome.review_items[0].repeats == "r7"


def test_a_repeat_of_an_unknown_rule_becomes_a_new_item(monkeypatch):
    known = [evaluator.KnownRule(id="r7", rule="past simple with a finished time expression")]
    item = ReviewItem(
        rule="third person -s", produced="She don't", correct="She doesn't", repeats="r99"
    )

    outcome, _ = _evaluate_with(monkeypatch, [item], known)

    assert outcome.review_items[0].repeats == ""


def test_incomplete_items_are_dropped_and_at_most_four_pass(monkeypatch):
    complete = [
        ReviewItem(rule=f"rule {n}", produced=f"wrong {n}", correct=f"right {n}") for n in range(6)
    ]
    incomplete = [
        ReviewItem(rule="", produced="x", correct="y"),
        ReviewItem(rule="rule", produced=" ", correct="y"),
        ReviewItem(rule="rule", produced="x", correct=""),
    ]

    outcome, _ = _evaluate_with(monkeypatch, incomplete + complete)

    assert [item.rule for item in outcome.review_items] == ["rule 0", "rule 1", "rule 2", "rule 3"]
