import pytest

from apps.catalog.models import Level, Scenario
from apps.agents.services.scenario_content import load_scenario_content

pytestmark = pytest.mark.django_db


def test_load_scenario_content_reads_real_catalog_content():
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)

    content = load_scenario_content(scenario, level)

    assert content.slug == "negociar-prazo"
    assert content.objective == scenario.objective
    assert content.max_turns == level.max_turns
    assert content.expected_cefr == level.expected_cefr
    assert content.role_keys() == ["rachel", "tom"]

    rachel = content.role("rachel")
    tom = content.role("tom")
    assert rachel.archetype == "Gatekeeper"
    assert rachel.scaffolds is False
    assert tom.archetype == "Aliado"
    assert tom.scaffolds is True

    # Nível 3 tem sobreposição de pesos para este cenário: vocabulary 10, pragmatics 15.
    assert content.weights["vocabulary"] == 10
    assert content.weights["pragmatics"] == 15
    assert sum(content.weights.values()) == 100

    assert {c.code for c in content.criteria} == {"c1", "c2", "c3", "c4"}


def test_load_scenario_content_applies_level_closing_hint_override_when_present():
    scenario = Scenario.objects.get(slug="entrevista-de-emprego")
    level = Level.objects.get(order=3)

    content = load_scenario_content(scenario, level)

    # Sem sobreposição cadastrada para este cenário e nível: usa o padrão do cenário.
    assert content.closing_hint == scenario.closing_hint


def test_interview_roles_carry_only_the_facts_their_function_would_know():
    scenario = Scenario.objects.get(slug="entrevista-de-emprego")

    content = load_scenario_content(scenario, Level.objects.get(order=2))

    rachel = content.role("rachel")
    tom = content.role("tom")
    assert "três etapas" in rachel.extra_instruction
    assert "PyTest" not in rachel.extra_instruction
    assert "PyTest" in tom.extra_instruction
    assert "três etapas" not in tom.extra_instruction


def test_content_carries_how_the_level_wants_the_persona_to_reply_to_the_student():
    scenario = Scenario.objects.get(slug="entrevista-de-emprego")

    replies = {
        order: load_scenario_content(scenario, Level.objects.get(order=order)).reply_to_student
        for order in (1, 2, 3)
    }

    assert "one short, simple sentence" in replies[1]
    assert "closed question" in replies[1]
    assert "invite the student to go on" not in replies[1]
    assert "invite the student to go on" in replies[2]
    assert "invite the student to go on" in replies[3]


def test_other_scenarios_keep_roles_without_extra_instruction():
    scenario = Scenario.objects.get(slug="negociar-prazo")

    content = load_scenario_content(scenario, Level.objects.get(order=2))

    assert all(role.extra_instruction == "" for role in content.roles)


def test_load_scenario_content_scopes_criteria_to_comprehension_level():
    scenario = Scenario.objects.get(slug="problema-no-quarto")
    level = Level.objects.get(order=1)

    content = load_scenario_content(scenario, level)

    assert {c.code for c in content.criteria} == {"c5"}
