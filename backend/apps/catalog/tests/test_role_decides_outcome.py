import importlib

import pytest
from django.apps import apps

from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.admin.scenario import ScenarioRoleInline
from apps.catalog.models import Level, Scenario, ScenarioRole

pytestmark = pytest.mark.django_db

_MIGRATION = importlib.import_module("apps.catalog.migrations.0017_seed_role_decides_outcome")


def _deciders(slug: str) -> set[str]:
    return set(
        ScenarioRole.objects.filter(scenario__slug=slug, decides_outcome=True).values_list(
            "persona__name", flat=True
        )
    )


def test_in_the_deadline_negotiation_only_the_pm_decides():
    assert _deciders("negociar-prazo") == {"Rachel"}


def test_in_the_interview_and_in_the_hotel_both_roles_decide():
    assert _deciders("entrevista-de-emprego") == {"Rachel", "Tom"}
    assert _deciders("problema-no-quarto") == {"Emma", "James"}


def test_a_new_role_does_not_decide_until_the_admin_marks_it():
    field = ScenarioRole._meta.get_field("decides_outcome")

    assert field.default is False
    assert "decide" in field.verbose_name


def test_undoing_the_data_migration_clears_the_mark_and_keeps_the_rest():
    before = ScenarioRole.objects.filter(scenario__slug="negociar-prazo").values_list(
        "pk", "concession", "extra_instruction"
    )
    before = set(before)

    _MIGRATION.unmark_deciders(apps, None)

    assert not ScenarioRole.objects.filter(decides_outcome=True).exists()
    after = set(
        ScenarioRole.objects.filter(scenario__slug="negociar-prazo").values_list(
            "pk", "concession", "extra_instruction"
        )
    )
    assert after == before

    _MIGRATION.mark_deciders(apps, None)

    assert _deciders("negociar-prazo") == {"Rachel"}


def test_the_admin_form_exposes_the_mark():
    assert "decides_outcome" in ScenarioRoleInline.fields


def test_content_carries_the_mark_and_the_archetype_description():
    content = load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )

    rachel, tom = content.role("rachel"), content.role("tom")

    assert rachel.decides_outcome is True
    assert tom.decides_outcome is False
    assert "apoia quando o argumento é bom" in tom.archetype_description
    assert [role.key for role in content.deciders()] == ["rachel"]
    assert content.decides("rachel") is True
    assert content.decides("tom") is False


def test_a_scenario_without_any_mark_treats_every_role_as_a_decider():
    ScenarioRole.objects.filter(scenario__slug="negociar-prazo").update(decides_outcome=False)
    content = load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )

    assert [role.key for role in content.deciders()] == ["rachel", "tom"]
    assert content.decides("tom") is True
