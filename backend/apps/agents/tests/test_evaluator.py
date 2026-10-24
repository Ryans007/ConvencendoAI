import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import evaluator
from apps.agents.services.schemas import DimensionScores, EvaluationResult, ReviewItem
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _FakeStructuredLLM:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        return self._result


def _full_scores(value: float = 5) -> DimensionScores:
    return DimensionScores(
        fluency=value, vocabulary=value, grammar=value, pragmatics=value, autonomy=value
    )


def _content():
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    return load_scenario_content(scenario, level)


def test_evaluate_clamps_scores_and_filters_invalid_criteria(monkeypatch):
    content = _content()
    fake_result = EvaluationResult(
        confirmed_criteria=["c1", "c2", "not-a-real-criterion"],
        sub_scores=DimensionScores(
            fluency=999, vocabulary=-5, grammar=10, pragmatics=3.6, autonomy=100
        ),
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
    fake_result = EvaluationResult(confirmed_criteria=[], sub_scores=_full_scores())
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
            return EvaluationResult(sub_scores=_full_scores())

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
            return EvaluationResult(sub_scores=_full_scores())

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
            return EvaluationResult(sub_scores=_full_scores(), review_items=review_items)

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


def test_the_prompt_asks_for_the_whole_sentence_and_a_correction_that_keeps_the_meaning(
    monkeypatch,
):
    _, prompt = _evaluate_with(monkeypatch, [])

    assert "the WHOLE sentence the student said" in prompt
    assert "never just the wrong word or fragment" in prompt
    assert "never change the request, the topic or the facts" in prompt


def test_the_prompt_never_turns_a_correct_sentence_into_a_review_item(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])
    flat = " ".join(prompt.split())

    assert "First make sure the sentence is really wrong" in flat
    assert "A sentence that is correct English is NOT a mistake" in flat
    assert '"I would like your phone number" is correct' in flat
    assert "Never invent a rule to justify an item" in flat


def test_the_prompt_asks_for_a_correction_that_only_changes_the_wrong_words(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])
    flat = " ".join(prompt.split())

    assert "Change ONLY the words that make the sentence wrong" in flat
    assert "never add a word the sentence did not need" in flat


def test_the_prompt_asks_for_a_portuguese_note_that_never_writes_the_correct_words(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])

    assert '"note": ONE short sentence in Brazilian Portuguese' in prompt
    flat = " ".join(prompt.split())
    assert "must NEVER contain the correct English word, phrase or structure" in flat


def test_the_prompt_treats_a_wrong_word_in_the_transcript_as_the_students_mistake(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])
    flat = " ".join(prompt.split())

    assert "automatic speech recognition heard" in flat
    assert "the only evidence you have" in flat
    assert "even when it may have been a mispronunciation" in flat
    assert "if you would be guessing, skip it" in flat


def test_the_prompt_asks_the_note_to_say_when_two_words_sound_alike(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])
    flat = " ".join(prompt.split())

    assert "When the wrong word sounds like the right one, say so" in flat
    assert "Bad:" in flat and "gives the answer away" in flat


def test_the_prompt_says_what_is_not_a_mistake_and_prefers_structure(monkeypatch):
    _, prompt = _evaluate_with(monkeypatch, [])

    assert "Never report rudeness, register" in prompt
    assert "prefer grammar structure mistakes" in prompt


def _item_with_note(note: str, produced: str, correct: str) -> ReviewItem:
    return ReviewItem(rule="rule", produced=produced, correct=correct, note=note)


def test_a_safe_note_is_kept(monkeypatch):
    item = _item_with_note(
        "Aqui o verbo é o de consertar, e não o de relatar.",
        "I want to report it today, please",
        "I want to repair it today, please",
    )

    outcome, _ = _evaluate_with(monkeypatch, [item])

    assert outcome.review_items[0].note == "Aqui o verbo é o de consertar, e não o de relatar."


def _note_of(monkeypatch, note: str, produced: str, correct: str) -> str:
    outcome, _ = _evaluate_with(monkeypatch, [_item_with_note(note, produced, correct)])
    return outcome.review_items[0].note


def test_the_word_that_fixes_the_mistake_is_masked_and_the_rest_of_the_note_stays(monkeypatch):
    note = _note_of(
        monkeypatch,
        "Use repair, que significa consertar.",
        "I want to report it today, please",
        "I want to repair it today, please",
    )

    assert note == "Use ___, que significa consertar."


def test_a_fixing_word_between_quotes_is_masked(monkeypatch):
    note = _note_of(
        monkeypatch,
        "Use 'repair', não 'report'.",
        "I want to report it today, please",
        "I want to repair it today, please",
    )

    assert note == "Use '___', não 'report'."


def test_an_inflection_of_the_fixing_word_is_masked_too(monkeypatch):
    note = _note_of(
        monkeypatch,
        "O verbo certo é repair, aqui no passado seria repaired.",
        "I want to report it today, please",
        "I want it repaired today, please",
    )

    assert note == "O verbo certo é ___, aqui no passado seria ___."


def test_the_mask_ignores_case_and_keeps_the_rest_of_the_note(monkeypatch):
    note = _note_of(monkeypatch, "Troque por Repair.", "I report it", "I repair it")

    assert note == "Troque por ___."


def test_a_word_that_only_starts_the_same_way_is_not_masked(monkeypatch):
    note = _note_of(
        monkeypatch,
        "Repare no verbo da frase.",
        "I report it",
        "I repair it",
    )

    assert note == "Repare no verbo da frase."


def test_a_long_unrelated_word_with_the_same_start_is_not_masked(monkeypatch):
    note = _note_of(
        monkeypatch,
        "Parâmetros diferentes pedem outra palavra.",
        "I use the para value",
        "I use the parameter value",
    )

    assert "___" not in note


def test_short_fixing_words_are_not_masked(monkeypatch):
    note = _note_of(
        monkeypatch,
        "Depois de listen, falta a preposição que liga ao objeto: to.",
        "You don't listen me",
        "You don't listen to me",
    )

    assert note == "Depois de listen, falta a preposição que liga ao objeto: to."


def test_the_item_keeps_its_sentences_when_the_note_is_masked(monkeypatch):
    item = _item_with_note(
        "Use repair.", "I want to report it today", "I want to repair it today"
    )

    outcome, _ = _evaluate_with(monkeypatch, [item])

    assert outcome.review_items[0].produced == "I want to report it today"
    assert outcome.review_items[0].correct == "I want to repair it today"


def test_an_item_without_a_note_is_still_valid(monkeypatch):
    item = ReviewItem(rule="rule", produced="She don't like it", correct="She doesn't like it")

    outcome, _ = _evaluate_with(monkeypatch, [item])

    assert len(outcome.review_items) == 1
    assert outcome.review_items[0].note == ""


def test_an_item_with_only_a_note_is_still_dropped(monkeypatch):
    item = ReviewItem(rule="rule", produced=" ", correct="x", note="Uma nota sozinha.")

    outcome, _ = _evaluate_with(monkeypatch, [item])

    assert outcome.review_items == []


class _SequenceLLM:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return self._results.pop(0)


def test_a_judge_that_returns_no_scores_is_asked_again_and_the_second_answer_is_used(monkeypatch):
    llm = _SequenceLLM([EvaluationResult(), EvaluationResult(sub_scores=_full_scores(4))])
    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: llm)

    outcome = evaluator.evaluate(_content(), [])

    assert llm.calls == 2
    assert {d.value for d in outcome.judged_dimensions} == {4}


def test_a_judge_that_never_returns_scores_fails_instead_of_grading_zero(monkeypatch):
    llm = _SequenceLLM([EvaluationResult(), EvaluationResult()])
    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: llm)

    with pytest.raises(evaluator.IncompleteEvaluation):
        evaluator.evaluate(_content(), [])

    assert llm.calls == 2


def test_a_dimension_the_judge_scored_zero_is_kept_as_zero(monkeypatch):
    scores = _full_scores(4)
    scores.grammar = 0
    llm = _SequenceLLM([EvaluationResult(sub_scores=scores)])
    monkeypatch.setattr(evaluator, "get_structured_llm", lambda purpose, schema: llm)

    outcome = evaluator.evaluate(_content(), [])

    assert llm.calls == 1
    assert {d.dimension: d.value for d in outcome.judged_dimensions}["grammar"] == 0
