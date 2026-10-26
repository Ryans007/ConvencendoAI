import importlib

import pytest
from django.apps import apps

from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.constants import RolePresence
from apps.catalog.models import Level, Persona, Scenario, ScenarioRole, Track
from apps.catalog.validators import CastEntry, clean_scenario_cast

pytestmark = pytest.mark.django_db

_MIGRATION = importlib.import_module("apps.catalog.migrations.0024_seed_supporting_scenes")

_CASTS = {
    "quarto-novo-barulhento": (("Emma", "James"), "Mike", "James"),
    "pedido-errado": (("Ben", "Olivia"), "Mia", "Olivia"),
    "reservar-aniversario": (("Olivia", "Ben"), "Mia", "Olivia"),
}


def _roles(slug: str):
    return ScenarioRole.objects.filter(scenario__slug=slug).select_related("persona")


@pytest.mark.parametrize("slug", list(_CASTS))
def test_each_new_scene_has_two_principals_a_supporting_role_and_one_decider(slug):
    principals, supporting, decider = _CASTS[slug]
    roles = list(_roles(slug).order_by("opening_order"))

    assert [role.persona.name for role in roles] == [*principals, supporting]
    assert [role.presence for role in roles] == [
        RolePresence.PRINCIPAL,
        RolePresence.PRINCIPAL,
        RolePresence.SUPPORTING,
    ]
    assert {role.persona.name for role in roles if role.decides_outcome} == {decider}
    assert roles[2].entry_cue
    assert not roles[0].entry_cue and not roles[1].entry_cue


@pytest.mark.parametrize("slug", list(_CASTS))
def test_each_new_cast_passes_the_cast_validation(slug):
    cast = [
        CastEntry(role.presence, role.decides_outcome, role.opening_order) for role in _roles(slug)
    ]

    clean_scenario_cast(cast)


@pytest.mark.parametrize("slug", list(_CASTS))
def test_the_three_roles_share_the_same_facts(slug):
    texts = set(_roles(slug).values_list("extra_instruction", flat=True))

    assert len(texts) == 1
    assert "todos os personagens da cena" in texts.pop()


@pytest.mark.parametrize("slug", list(_CASTS))
def test_voices_are_distinct_inside_each_scene(slug):
    voices = list(_roles(slug).values_list("persona__voice", flat=True))

    assert len(set(voices)) == len(voices) == 3


@pytest.mark.parametrize("slug", list(_CASTS))
def test_criteria_follow_the_level_split(slug):
    scenario = Scenario.objects.get(slug=slug)
    level_1 = Level.objects.get(order=1)

    for criterion in scenario.criteria.all():
        orders = sorted(criterion.levels.values_list("order", flat=True))
        assert orders == ([1] if criterion.code == "c5" else [2, 3])
    assert scenario.criteria.count() == 5
    assert scenario.criteria.filter(levels=level_1).count() == 1


def test_the_hotel_continues_in_the_same_track_right_after_the_first_scene():
    first = Scenario.objects.get(slug="problema-no-quarto")
    second = Scenario.objects.get(slug="quarto-novo-barulhento")

    assert second.track_id == first.track_id
    assert (first.order, second.order) == (1, 2)
    assert "Se você tinha escolhido o conserto" in second.context


def test_the_restaurant_track_comes_after_travel_with_both_scenes_in_order():
    track = Track.objects.get(slug="restaurante-e-servicos")

    assert track.order == 3
    assert "Nova York" in track.student_role
    assert list(track.scenarios.order_by("order").values_list("slug", flat=True)) == [
        "pedido-errado",
        "reservar-aniversario",
    ]


def test_the_engine_reads_the_supporting_role_of_a_new_scene():
    content = load_scenario_content(
        Scenario.objects.get(slug="pedido-errado"), Level.objects.get(order=2)
    )

    supporting = content.supporting_role()

    assert supporting is not None and supporting.name == "Mia"
    assert set(content.principal_keys()) == {
        role.key for role in content.roles if role.name in {"Ben", "Olivia"}
    }


def test_applying_twice_changes_nothing():
    counts = (Track.objects.count(), Persona.objects.count(), ScenarioRole.objects.count())

    _MIGRATION.seed_supporting_scenes(apps, None)

    assert (
        Track.objects.count(),
        Persona.objects.count(),
        ScenarioRole.objects.count(),
    ) == counts


def test_undoing_removes_only_what_the_migration_created():
    before = set(
        ScenarioRole.objects.exclude(scenario__slug__in=list(_CASTS)).values_list(
            "pk", "extra_instruction", "decides_outcome"
        )
    )

    _MIGRATION.remove_supporting_scenes(apps, None)

    assert not Scenario.objects.filter(slug__in=list(_CASTS)).exists()
    assert not Track.objects.filter(slug="restaurante-e-servicos").exists()
    assert not Persona.objects.filter(name__in=["Mike", "Ben", "Olivia", "Mia"]).exists()
    assert set(Persona.objects.values_list("name", flat=True)) == {
        "Rachel",
        "Tom",
        "Emma",
        "James",
    }
    assert (
        set(ScenarioRole.objects.values_list("pk", "extra_instruction", "decides_outcome"))
        == before
    )
