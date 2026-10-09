import pytest

from apps.agents.services import review_teacher
from apps.agents.services.review_teacher import ReviewJudgmentFailed, judge_review_answer
from apps.agents.services.schemas import ReviewVerdict

RULE = "past simple with a finished time expression"
SAID = "I have worked there yesterday"
CORRECT = "I worked there yesterday."

HINT = "Repare em yesterday: ele marca um tempo que já terminou."
HIT = "Certo, com yesterday o tempo já terminou e o passado simples é o correto."
GIVES_ANSWER = "Tente assim: I worked there yesterday, porque o tempo já terminou."


class _FakeLlm:
    def __init__(self, *verdicts: ReviewVerdict):
        self.prompts: list[str] = []
        self._verdicts = iter(verdicts)

    def invoke(self, messages):
        self.prompts.append(messages[0].content)
        return next(self._verdicts)


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*verdicts: ReviewVerdict) -> _FakeLlm:
        llm = _FakeLlm(*verdicts)
        monkeypatch.setattr(review_teacher, "get_structured_llm", lambda purpose, schema: llm)
        return llm

    return install


def _judge(step: int = 1, attempt: int = 1, heard: str = "I worked there yesterday"):
    return judge_review_answer(
        rule=RULE, said=SAID, correct=CORRECT, step=step, attempt=attempt, heard=heard
    )


def _wrong(feedback: str) -> ReviewVerdict:
    return ReviewVerdict(correct=False, feedback=feedback, correction=CORRECT)


def test_a_correct_verdict_comes_back_as_the_model_gave_it(fake_llm):
    fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    verdict = _judge()

    assert verdict.correct is True
    assert verdict.feedback == HIT


def test_the_step_one_prompt_asks_to_fix_the_rule_and_hints_on_the_first_miss(fake_llm):
    llm = fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    _judge(step=1, attempt=1)

    prompt = llm.prompts[0]
    assert "Step 1." in prompt and "Step 2." not in prompt
    assert "FIRST attempt" in prompt and "LAST attempt" not in prompt
    assert RULE in prompt and SAID in prompt and CORRECT in prompt
    assert "NEVER comment on pronunciation" in prompt


def test_the_step_two_prompt_asks_for_a_new_sentence_and_explains_on_the_last_miss(fake_llm):
    llm = fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    _judge(step=2, attempt=2, heard="Last week I finished the project")

    prompt = llm.prompts[0]
    assert "Step 2." in prompt and "Step 1." not in prompt
    assert "LAST attempt" in prompt and "FIRST attempt" not in prompt
    assert "Last week I finished the project" in prompt


def test_repeating_the_step_one_sentence_in_step_two_is_refused_without_the_model(fake_llm):
    llm = fake_llm()

    verdict = _judge(step=2, attempt=1, heard="i worked there, yesterday")

    assert verdict.correct is False
    assert "frase nova" in verdict.feedback
    assert verdict.correction == CORRECT
    assert llm.prompts == []


def test_feedback_in_english_is_asked_again(fake_llm):
    llm = fake_llm(_wrong("Look at the time word, it is finished and needs the past."), _wrong(HINT))

    verdict = _judge()

    assert verdict.feedback == HINT
    assert len(llm.prompts) == 2


def test_a_first_miss_hint_that_gives_the_correct_form_is_asked_again(fake_llm):
    llm = fake_llm(_wrong(GIVES_ANSWER), _wrong(HINT))

    verdict = _judge(attempt=1)

    assert verdict.feedback == HINT
    assert len(llm.prompts) == 2


def test_the_last_miss_may_show_the_correct_form_in_the_explanation(fake_llm):
    llm = fake_llm(_wrong(GIVES_ANSWER))

    verdict = _judge(attempt=2)

    assert verdict.feedback == GIVES_ANSWER
    assert len(llm.prompts) == 1


def test_a_correct_answer_may_quote_the_correct_form(fake_llm):
    llm = fake_llm(ReviewVerdict(correct=True, feedback=GIVES_ANSWER))

    verdict = _judge(attempt=1)

    assert verdict.correct is True
    assert len(llm.prompts) == 1


def test_after_the_last_try_a_generic_portuguese_feedback_replaces_the_bad_one(fake_llm):
    english = "Look at the time word, it is finished and needs the past."
    llm = fake_llm(*[_wrong(english)] * review_teacher.MAX_TRIES)

    verdict = _judge(attempt=1)

    assert len(llm.prompts) == review_teacher.MAX_TRIES
    assert verdict.correct is False
    assert verdict.feedback == "Ainda não. Releia a regra desta frase e tente de novo."


def test_the_generic_feedback_of_a_correct_answer_confirms_it(fake_llm):
    english = "Great, the past simple is right with a finished time."
    fake_llm(*[ReviewVerdict(correct=True, feedback=english)] * review_teacher.MAX_TRIES)

    verdict = _judge()

    assert verdict.correct is True
    assert verdict.feedback.startswith("Certo")


def test_an_empty_verdict_is_a_failure_and_not_a_wrong_answer(fake_llm):
    fake_llm(*[ReviewVerdict()] * review_teacher.MAX_TRIES)

    with pytest.raises(ReviewJudgmentFailed):
        _judge()


def test_portuguese_feedback_quoting_english_examples_is_not_taken_for_english(fake_llm):
    quoting = (
        "Você usou a estrutura correta: need + person + to + verb. "
        "Em 'I need you to go' a pessoa vem antes de to."
    )
    llm = fake_llm(ReviewVerdict(correct=True, feedback=quoting))

    verdict = _judge()

    assert verdict.feedback == quoting
    assert len(llm.prompts) == 1


def test_english_text_outside_the_quotes_is_still_refused(fake_llm):
    llm = fake_llm(
        _wrong("Look at the word 'yesterday', it needs the past form of the verb."),
        _wrong(HINT),
    )

    verdict = _judge()

    assert verdict.feedback == HINT
    assert len(llm.prompts) == 2


def test_the_note_already_shown_goes_into_the_prompt_with_the_request_not_to_repeat_it(fake_llm):
    llm = fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    judge_review_answer(
        rule=RULE,
        said=SAID,
        correct=CORRECT,
        note="Repare no tempo da frase.",
        step=1,
        attempt=1,
        heard="I worked there yesterday",
    )

    prompt = llm.prompts[0]
    assert "ALREADY SHOWN TO THE STUDENT" in prompt
    assert '"Repare no tempo da frase."' in prompt
    assert "Do not repeat it" in prompt


def test_without_a_note_the_prompt_has_no_such_block(fake_llm):
    llm = fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    _judge()

    assert "ALREADY SHOWN TO THE STUDENT" not in llm.prompts[0]


def test_a_blank_note_adds_no_block(fake_llm):
    llm = fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    judge_review_answer(
        rule=RULE, said=SAID, correct=CORRECT, note="   ", step=1, attempt=1, heard="x"
    )

    assert "ALREADY SHOWN" not in llm.prompts[0]


def test_the_first_miss_of_an_item_with_a_note_points_to_the_context_on_the_card(fake_llm):
    llm = fake_llm(_wrong(HINT))

    verdict = judge_review_answer(
        rule=RULE,
        said=SAID,
        correct=CORRECT,
        note="Repare no tempo da frase.",
        step=1,
        attempt=1,
        heard="I have worked there yesterday",
    )

    assert verdict.feedback == "Ainda não. Releia o contexto acima e tente de novo."
    assert verdict.correct is False
    assert verdict.correction == CORRECT
    assert len(llm.prompts) == 1


def test_the_first_miss_with_a_note_does_not_retry_for_a_hint_that_will_be_replaced(fake_llm):
    llm = fake_llm(_wrong("Look at the time word, it is finished."))

    verdict = judge_review_answer(
        rule=RULE, said=SAID, correct=CORRECT, note="Uma nota.", step=1, attempt=1, heard="x"
    )

    assert verdict.feedback.startswith("Ainda não")
    assert len(llm.prompts) == 1


def test_the_first_miss_without_a_note_keeps_the_teachers_hint(fake_llm):
    fake_llm(_wrong(HINT))

    verdict = _judge(attempt=1)

    assert verdict.feedback == HINT


def test_the_last_miss_with_a_note_keeps_the_teachers_explanation(fake_llm):
    fake_llm(_wrong(GIVES_ANSWER))

    verdict = judge_review_answer(
        rule=RULE, said=SAID, correct=CORRECT, note="Uma nota.", step=1, attempt=2, heard="x"
    )

    assert verdict.feedback == GIVES_ANSWER


def test_a_correct_answer_with_a_note_keeps_the_teachers_confirmation(fake_llm):
    fake_llm(ReviewVerdict(correct=True, feedback=HIT))

    verdict = judge_review_answer(
        rule=RULE, said=SAID, correct=CORRECT, note="Uma nota.", step=1, attempt=1, heard="x"
    )

    assert verdict.feedback == HIT


def test_an_empty_verdict_with_a_note_is_still_a_failure(fake_llm):
    fake_llm(*[ReviewVerdict()] * review_teacher.MAX_TRIES)

    with pytest.raises(ReviewJudgmentFailed):
        judge_review_answer(
            rule=RULE, said=SAID, correct=CORRECT, note="Uma nota.", step=1, attempt=1, heard="x"
        )
