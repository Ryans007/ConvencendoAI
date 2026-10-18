from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services import personas as personas_service
from apps.agents.services.personas import (
    TRANSCRIPTION_NOTICE,
    build_system_prompt,
    generate_closing_hint_line,
    generate_closing_line,
)
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import ClosingLine
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


def test_facts_block_lets_the_persona_answer_and_ask_about_experience_but_not_invent():
    prompt = _prompt_with_extra_instruction(_FACTS)

    block = prompt[prompt.index("MORE ABOUT YOUR ROLE") : prompt.index(_FACTS)]
    assert "ONLY to answer what the student asks you" in block
    assert "ask about their own experience when it fits your role" in block
    assert "never invent a fact that is not here" in block
    assert "Never build your own questions from them" not in block


def test_role_without_extra_instruction_adds_no_block():
    prompt = _prompt_with_extra_instruction("")

    assert "MORE ABOUT YOUR ROLE" not in prompt


def test_blank_extra_instruction_adds_no_block():
    prompt = _prompt_with_extra_instruction("   \n ")

    assert "MORE ABOUT YOUR ROLE" not in prompt


def test_technical_questions_are_allowed_but_never_as_an_exam():
    prompt = _prompt_with_extra_instruction(_FACTS)

    assert "YOU ARE NOT AN EXAMINER" not in prompt
    assert "TECHNICAL QUESTIONS" in prompt
    assert "ask about their technical choices and about alternatives" in prompt
    assert "never ask whether they know a concept" in prompt
    assert "did not mention" not in prompt


def test_the_persona_is_told_to_use_what_the_student_already_said():
    prompt = _prompt(3)

    assert "NEVER ASK FOR WHAT YOU ALREADY KNOW" in prompt
    assert prompt.index("\nCRITICAL RULES\n") < prompt.index("NEVER ASK FOR WHAT YOU ALREADY KNOW")
    assert 'after "my room 312", never' in prompt


def test_asking_if_the_english_is_correct_is_not_a_request_for_correction():
    prompt = _prompt(3)

    assert "IF THE STUDENT ASKS WHETHER THEIR ENGLISH IS CORRECT" in prompt
    assert prompt.index("\nCRITICAL RULES\n") < prompt.index("WHETHER THEIR ENGLISH IS CORRECT")
    assert 'Never say "your English is good /' in prompt
    assert 'fine / clear / understandable"' in prompt
    assert "never repeat\n  their sentence in a better form" in prompt
    assert "say that you understood\n  what they said" in prompt


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

        rule = " ".join(prompt[prompt.index("ANSWER THE STUDENT FIRST") :].split())
        assert "unless you are resolving the scene, ALWAYS" in rule
        assert "leaves the student with nothing to say" in rule


def test_the_line_that_resolves_the_scene_asks_nothing():
    for level_order in (1, 2, 3):
        prompt = " ".join(_prompt(level_order).split())

        exception = 'The only exception is the line that resolves the scene (see "scene_resolved"'
        assert exception in prompt
        resolved_rule = prompt[prompt.index('- "scene_resolved"') :]
        assert "close the interaction naturally, with NO question" in resolved_rule
        assert "the session ends right after it" in resolved_rule


def test_an_invitation_to_go_on_counts_as_the_turns_question():
    prompt = _prompt(3)

    assert 'An invitation to the student to go on' in prompt
    assert "counts as this turn's question" in prompt


def test_the_persona_is_never_asked_to_write_a_hint_for_the_student():
    for level_order in (1, 2, 3):
        prompt = _prompt(level_order)

        assert '"hint"' not in prompt
        assert "PORTUGUESE" not in prompt
        assert "goes only in the hint" not in prompt


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
        return ClosingLine(line="Sure. Do you have any questions for us?")


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

    generate_closing_hint_line(content, role, history)

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


def _closing_line_prompt(monkeypatch) -> str:
    content = _content()
    prompts = []
    monkeypatch.setattr(
        personas_service, "get_structured_llm", lambda purpose, schema: _CapturingLLM(prompts)
    )
    history = [
        AIMessage(content="[Rachel] Which floor would you like?"),
        HumanMessage(content="I won a wood floor."),
    ]

    generate_closing_line(content, content.roles[0], history)

    return prompts[0]


def test_the_main_prompt_carries_the_transcription_notice_before_the_critical_rules():
    prompt = _prompt_with_extra_instruction("")

    assert TRANSCRIPTION_NOTICE in prompt
    assert prompt.index(TRANSCRIPTION_NOTICE) < prompt.index("\nCRITICAL RULES\n")


def test_the_time_limit_closing_prompt_carries_the_transcription_notice(monkeypatch):
    assert TRANSCRIPTION_NOTICE in _closing_line_prompt(monkeypatch)


def test_the_closing_hint_prompt_carries_the_transcription_notice(monkeypatch):
    assert TRANSCRIPTION_NOTICE in _closing_hint_prompt(monkeypatch, "")


def test_the_notice_says_what_the_transcription_is_and_forbids_commenting_on_it():
    assert "automatic voice transcription" in TRANSCRIPTION_NOTICE
    assert '"I won" for "I want"' in TRANSCRIPTION_NOTICE
    assert "Never mention, correct or comment on the transcription" in TRANSCRIPTION_NOTICE


def _deadline_prompt(role_key: str, level_order: int = 3) -> str:
    content = load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=level_order)
    )
    return build_system_prompt(content, content.role(role_key), memory="")


def test_the_prompt_carries_the_archetype_with_its_description():
    prompt = _deadline_prompt("tom")

    assert "Your interactional role in this scene: Aliado." in prompt
    assert "apoia quando o argumento é bom" in prompt


def test_the_role_that_decides_is_told_to_concede_when_the_condition_is_met():
    prompt = _deadline_prompt("rachel")

    assert "You decide this." in prompt
    assert "resistance ENDS the moment" in prompt
    assert "CONCESSION CHECK: split what makes you concede into its parts" in prompt
    assert 'Fill "condition_met" first' in prompt
    assert "concede in THAT very line" in prompt
    assert 'set "scene_resolved" to true and ask NO question' in prompt
    assert "Concede as soon as the student meets what makes you concede" in prompt
    assert "Do not hand it over easily" not in prompt


def test_the_role_that_does_not_decide_never_grants_or_confirms_the_outcome():
    prompt = _deadline_prompt("tom")

    assert "You do NOT decide this: Rachel (key: rachel) does." in prompt
    assert 'always answer "condition_met": false and "scene_resolved":\nfalse' in prompt
    assert "CONCESSION CHECK" not in prompt
    assert "Concede as soon as" not in prompt
    assert "Do not hand it over easily" not in prompt


def test_in_a_scenario_where_both_roles_decide_both_get_the_deciders_block():
    content = _content()

    for role in content.roles:
        prompt = build_system_prompt(content, role, memory="")

        assert "You decide this." in prompt
