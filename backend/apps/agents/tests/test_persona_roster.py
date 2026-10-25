import pytest

from apps.agents.services.personas import build_system_prompt
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.tests.three_roles import hotel_with_porter
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


def _interview():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


def test_with_three_characters_the_persona_meets_both_others_by_name_and_function():
    content = hotel_with_porter()
    emma = content.role("emma")

    prompt = build_system_prompt(content, emma, memory="")

    assert "The other people in the room:" in prompt
    assert f"- James (key: james), {content.role('james').scene_function}" in prompt
    assert "- Mike (key: mike), carregador de malas; a supporting character" in prompt


def test_the_supporting_character_meets_the_two_principals():
    content = hotel_with_porter()

    prompt = build_system_prompt(content, content.role("mike"), memory="")

    assert "- Emma (key: emma)" in prompt
    assert "- James (key: james)" in prompt
    assert "a supporting character" not in prompt


def test_with_two_characters_the_persona_still_meets_the_other_one():
    content = _interview()
    rachel, tom = content.roles

    prompt = build_system_prompt(content, rachel, memory="")

    assert f"The other person in the room: Tom (key: tom), {tom.scene_function}." in prompt


@pytest.mark.parametrize(
    "flags",
    [{}, {"addressed_by_student": True}],
)
def test_no_prompt_speaks_of_the_other_character(flags):
    content = hotel_with_porter()
    for role in content.roles:
        prompt = build_system_prompt(content, role, memory="", **flags)

        assert "the other character" not in prompt.lower()


def test_the_handoff_instruction_names_who_receives_the_floor():
    content = hotel_with_porter()

    prompt = build_system_prompt(
        content, content.role("emma"), memory="", hand_floor_to=content.role("james")
    )

    assert "YOU HAND THE FLOOR TO James NOW" in prompt
