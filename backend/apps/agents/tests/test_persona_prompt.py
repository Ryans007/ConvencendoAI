from dataclasses import replace

import pytest

from apps.agents.services.personas import build_system_prompt
from apps.agents.services.scenario_content import load_scenario_content
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
