from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import personas as personas_service
from apps.agents.services.personas import build_system_prompt, generate_closing_hint_turn
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import ClosingHintTurn
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db

_FACTS = "O time usa Python, Django e PyTest. São seis pessoas."


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=1)
    )


def _prompt_with_extra_instruction(extra_instruction: str) -> str:
    content = _content()
    role = replace(content.roles[0], extra_instruction=extra_instruction)
    return build_system_prompt(content, role, memory="")


def test_extra_instruction_reaches_the_prompt_before_the_critical_rules():
    prompt = _prompt_with_extra_instruction(_FACTS)

    assert "MORE ABOUT YOUR ROLE IN THIS SCENE" in prompt
    assert _FACTS in prompt
    assert prompt.index(_FACTS) < prompt.index("CRITICAL RULES")


def test_facts_block_says_the_facts_are_only_for_answering_and_never_for_own_questions():
    prompt = _prompt_with_extra_instruction(_FACTS)

    block = prompt[prompt.index("MORE ABOUT YOUR ROLE") : prompt.index(_FACTS)]
    assert "ONLY to answer what the student asks you" in block
    assert "Never build your own questions from them" in block


def test_role_without_extra_instruction_adds_no_block():
    prompt = _prompt_with_extra_instruction("")

    assert "MORE ABOUT YOUR ROLE" not in prompt


def test_blank_extra_instruction_adds_no_block():
    prompt = _prompt_with_extra_instruction("   \n ")

    assert "MORE ABOUT YOUR ROLE" not in prompt


def test_technology_rule_restricts_the_persona_questions_not_the_answers():
    prompt = _prompt_with_extra_instruction(_FACTS)

    assert "into a\n  question you ask them" in prompt
    assert "you may state the facts you know about the scene" in prompt


def _prompt(level_order: int = 1, **flags) -> str:
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=level_order)
    )
    return build_system_prompt(content, content.roles[0], memory="", **flags)


def test_answer_first_rule_carries_the_level_instruction_for_replying():
    level_one = _prompt(1)
    level_three = _prompt(3)

    assert "ANSWER THE STUDENT FIRST" in level_one
    assert "Answer in one short, simple sentence." in level_one
    assert "Answer with the detail the question needs" in level_three
    assert "Answer with the detail the question needs" not in level_one


def test_answer_first_rule_is_among_the_critical_rules():
    prompt = _prompt(2)

    assert prompt.index("\nCRITICAL RULES\n") < prompt.index("ANSWER THE STUDENT FIRST")
    assert prompt.index("- QUESTION FORMAT (") < prompt.index("ANSWER THE STUDENT FIRST")


def test_answering_the_student_never_replaces_the_question_or_the_invitation():
    for level_order in (1, 2, 3):
        prompt = _prompt(level_order)

        rule = prompt[prompt.index("ANSWER THE STUDENT FIRST") :]
        assert "Then ALWAYS finish the line with this turn's" in rule
        assert "leaves the student with\n  nothing to say" in rule


def test_an_invitation_to_go_on_counts_as_the_turns_question():
    prompt = _prompt(3)

    assert 'An invitation to the student to go on' in prompt
    assert "counts as this turn's question" in prompt


def test_hint_rule_covers_a_line_that_ends_with_an_invitation():
    prompt = _prompt(3)

    assert "ends with an invitation instead of a question" in prompt


def test_notice_that_the_student_is_talking_to_the_persona_appears_only_when_flagged():
    assert "THE STUDENT IS TALKING TO YOU" not in _prompt(1)
    flagged = _prompt(1, addressed_by_student=True)

    assert "THE STUDENT IS TALKING TO YOU" in flagged
    assert "do not\nhand the floor to the other character" in flagged


class _CapturingLLM:
    def __init__(self, prompts: list):
        self._prompts = prompts

    def invoke(self, messages):
        self._prompts.append(messages[0].content)
        return ClosingHintTurn(line="Sure. Do you have any questions for us?", hint="dica")


def _closing_hint_prompt(monkeypatch, extra_instruction: str) -> str:
    content = _content()
    role = replace(content.roles[0], extra_instruction=extra_instruction)
    prompts = []
    monkeypatch.setattr(
        personas_service, "get_structured_llm", lambda purpose, schema: _CapturingLLM(prompts)
    )
    history = [
        AIMessage(content="[Rachel] Tell me about your last project."),
        HumanMessage(content="What are the next steps in the process?"),
    ]

    generate_closing_hint_turn(content, role, history)

    return prompts[0]


def test_closing_hint_turn_answers_the_student_before_the_invitation(monkeypatch):
    prompt = _closing_hint_prompt(monkeypatch, _FACTS)

    assert "What are the next steps in the process?" in prompt
    assert "start with\none short sentence that answers it or reacts to it" in prompt
    assert prompt.index("answers it or reacts to it") < prompt.index("MUST do exactly this")


def test_closing_hint_turn_carries_the_role_facts_only_for_answering(monkeypatch):
    prompt = _closing_hint_prompt(monkeypatch, _FACTS)

    assert _FACTS in prompt
    assert "Use it only to answer the student, never to build your own question" in prompt


def test_closing_hint_turn_without_facts_has_no_facts_block(monkeypatch):
    prompt = _closing_hint_prompt(monkeypatch, "")

    assert "WHAT YOU KNOW ABOUT THIS SCENE" not in prompt
