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
        assert "Then ALWAYS finish the line with this turn's question" in rule
        assert "leaves the student with nothing to say" in rule


def test_no_prompt_lets_the_persona_end_the_scene():
    for level_order in (1, 2, 3):
        prompt = _prompt(level_order)

        assert "scene_resolved" not in prompt
        assert "resolves the scene" not in prompt
        assert "close the interaction" not in prompt


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
    assert "do not\nhand the floor to anyone else" in flagged


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


def test_the_role_that_decides_gets_its_card_and_no_push_to_concede():
    prompt = _deadline_prompt("rachel")

    assert "You decide this." in prompt
    assert "What makes you concede:" in prompt
    assert "resistance ENDS" not in prompt
    assert "CONCESSION CHECK" not in prompt
    assert "condition_met" not in prompt
    assert "Concede as soon as" not in prompt
    assert "Do not hand it over easily" not in prompt


def test_the_role_that_does_not_decide_never_grants_or_confirms_the_outcome():
    prompt = _deadline_prompt("tom")

    assert "You do NOT decide this: Rachel (key: rachel) does." in prompt
    assert "condition_met" not in prompt
    assert "CONCESSION CHECK" not in prompt
    assert "Concede as soon as" not in prompt
    assert "Do not hand it over easily" not in prompt


def test_in_a_scenario_where_both_roles_decide_both_get_the_deciders_block():
    content = _content()

    for role in content.roles:
        prompt = build_system_prompt(content, role, memory="")

        assert "You decide this." in prompt


def _interview_prompt(role_key: str, history: list, **flags) -> str:
    from apps.agents.services.participation import scene_participation

    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    participation = scene_participation(content, role_key, history)
    return build_system_prompt(
        content, content.role(role_key), memory="", participation=participation, **flags
    )


_RACHEL_ONLY = [
    AIMessage(content="[Rachel] Hi, I'm Rachel from HR. Can you tell me about yourself?"),
    HumanMessage(content="I built a REST API with Django."),
]


def test_a_persona_that_has_not_spoken_yet_is_told_to_introduce_herself():
    prompt = _interview_prompt("tom", _RACHEL_ONLY)

    assert "THIS IS YOUR FIRST LINE IN THE CONVERSATION" in prompt
    assert 'introducing yourself in a few words: your name' in prompt
    assert "Hi, I'm Tom, the <your role in English>." in prompt
    assert "tech lead do time de backend" in prompt


def test_a_persona_that_already_spoke_is_not_told_to_introduce_herself_again():
    history = [
        *_RACHEL_ONLY,
        AIMessage(content="[Tom] Hi, I'm Tom, the tech lead. What did you build?"),
        HumanMessage(content="An order tracking API."),
    ]

    assert "FIRST LINE IN THE CONVERSATION" not in _interview_prompt("tom", history)
    assert "FIRST LINE IN THE CONVERSATION" not in _interview_prompt("rachel", history)


def test_the_debut_notice_does_not_depend_on_why_the_persona_entered():
    for flags in ({}, {"addressed_by_student": True}):
        prompt = _interview_prompt("tom", _RACHEL_ONLY, **flags)

        assert "FIRST LINE IN THE CONVERSATION" in prompt


def test_the_persona_that_receives_the_topic_is_also_told_to_introduce_herself():
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    prompt = _interview_prompt("tom", _RACHEL_ONLY, received_from=content.role("rachel"))

    assert "Rachel JUST HANDED THE FLOOR TO YOU" in prompt
    assert "FIRST LINE IN THE CONVERSATION" in prompt


def test_the_persona_that_only_redirects_gets_no_debut_notice():
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    prompt = _interview_prompt("tom", _RACHEL_ONLY, redirect_to=content.role("rachel"))

    assert "THIS SUBJECT IS NOT YOUR AREA" in prompt
    assert "FIRST LINE IN THE CONVERSATION" not in prompt


def test_the_persona_that_hands_the_floor_reacts_names_the_colleague_and_asks_nothing():
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    history = [
        AIMessage(content="[Rachel] Did you work in a team on that project?"),
        HumanMessage(content="Yes, I did."),
    ]
    prompt = _interview_prompt("rachel", history, hand_floor_to=content.role("tom"))

    assert "YOU HAND THE FLOOR TO Tom NOW" in prompt
    assert "with NO question" in prompt
    assert "react to what the student just said" in prompt
    assert "Never reuse a sentence" in prompt


def test_the_persona_that_hands_the_floor_gets_no_debut_notice():
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    prompt = _interview_prompt("tom", _RACHEL_ONLY, hand_floor_to=content.role("rachel"))

    assert "YOU HAND THE FLOOR TO Rachel NOW" in prompt
    assert "FIRST LINE IN THE CONVERSATION" not in prompt


def test_the_persona_that_does_not_hand_the_floor_gets_no_handoff_block():
    assert "YOU HAND THE FLOOR" not in _interview_prompt("rachel", _RACHEL_ONLY)


def test_the_opening_line_gets_no_debut_notice():
    assert "FIRST LINE IN THE CONVERSATION" not in _prompt(3)


def test_the_closing_hint_prompt_keeps_the_scene_direction_out_of_the_line(monkeypatch):
    prompt = _closing_hint_prompt(monkeypatch, "")

    assert "stage direction for you, never something to say out loud" in prompt
    assert "Never tell the student that the conversation is ending" in prompt


def test_the_time_limit_closing_prompt_answers_a_greeting_first(monkeypatch):
    prompt = _closing_line_prompt(monkeypatch)

    assert "asked you something, greeted you" in prompt
    assert prompt.index("greeted you") < prompt.index("what happens next")
