import pytest
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.catalog.admin.scenario import ScenarioRoleFormSet, ScenarioRoleInline
from apps.catalog.constants import RolePresence
from apps.catalog.models import Archetype, Persona, Scenario, ScenarioRole
from apps.catalog.validators import CastEntry, clean_scenario_cast

PRINCIPAL = RolePresence.PRINCIPAL
SUPPORTING = RolePresence.SUPPORTING


def _entry(presence: str, order: int, decides: bool = False) -> CastEntry:
    return CastEntry(presence=presence, decides_outcome=decides, opening_order=order)


def _messages(cast: list[CastEntry]) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        clean_scenario_cast(cast)
    return caught.value.messages


def test_two_principals_are_a_valid_cast():
    clean_scenario_cast([_entry(PRINCIPAL, 1, True), _entry(PRINCIPAL, 2, True)])


def test_two_principals_and_one_supporting_role_are_a_valid_cast():
    clean_scenario_cast(
        [_entry(PRINCIPAL, 1), _entry(PRINCIPAL, 2, True), _entry(SUPPORTING, 3)]
    )


def test_a_fourth_role_is_refused():
    cast = [
        _entry(PRINCIPAL, 1),
        _entry(PRINCIPAL, 2),
        _entry(SUPPORTING, 3),
        _entry(SUPPORTING, 4),
    ]

    assert "Um cenário tem no máximo 3 papéis." in _messages(cast)


def test_three_principals_are_refused():
    messages = _messages([_entry(PRINCIPAL, 1), _entry(PRINCIPAL, 2), _entry(PRINCIPAL, 3)])

    assert any("o terceiro papel precisa ser coadjuvante" in message for message in messages)


def test_two_supporting_roles_are_refused():
    messages = _messages([_entry(PRINCIPAL, 1), _entry(SUPPORTING, 2), _entry(SUPPORTING, 3)])

    assert "Um cenário tem no máximo um papel coadjuvante." in messages


def test_a_supporting_role_that_decides_is_refused():
    messages = _messages([_entry(PRINCIPAL, 1), _entry(PRINCIPAL, 2), _entry(SUPPORTING, 3, True)])

    assert messages == ["O coadjuvante não decide o resultado da cena."]


def test_a_supporting_role_that_opens_the_scene_is_refused():
    messages = _messages([_entry(SUPPORTING, 1), _entry(PRINCIPAL, 2), _entry(PRINCIPAL, 3)])

    assert messages == ["A cena abre com uma persona principal, não com o coadjuvante."]


@pytest.mark.django_db
def test_existing_roles_are_principal_without_an_entry_cue():
    roles = ScenarioRole.objects.all()

    assert roles.exists()
    assert set(roles.values_list("presence", flat=True)) == {PRINCIPAL}
    assert set(roles.values_list("entry_cue", flat=True)) == {""}


def test_the_admin_shows_the_new_fields_and_validates_the_cast():
    assert ScenarioRoleInline.formset is ScenarioRoleFormSet
    assert {"presence", "entry_cue"} <= set(ScenarioRoleInline.fields)
    assert ScenarioRole._meta.get_field("presence").verbose_name == "presença na cena"
    assert ScenarioRole._meta.get_field("entry_cue").verbose_name == "deixa de entrada"


def _formset_data(scenario: Scenario, extra_rows: list[dict]) -> dict:
    roles = list(scenario.roles.order_by("opening_order"))
    rows = [
        {
            "id": str(role.id),
            "persona": str(role.persona_id),
            "archetype": str(role.archetype_id),
            "scene_function": role.scene_function,
            "traits": role.traits,
            "resistance": role.resistance,
            "concession": role.concession,
            "presence": role.presence,
            "opening_order": str(role.opening_order),
            **({"decides_outcome": "on"} if role.decides_outcome else {}),
        }
        for role in roles
    ] + extra_rows
    data = {
        "roles-TOTAL_FORMS": str(len(rows)),
        "roles-INITIAL_FORMS": str(len(roles)),
        "roles-MIN_NUM_FORMS": "0",
        "roles-MAX_NUM_FORMS": "1000",
    }
    for index, row in enumerate(rows):
        for field, value in row.items():
            data[f"roles-{index}-{field}"] = value
    return data


def _new_row(persona: Persona, presence: str, order: int, decides: bool = False) -> dict:
    row = {
        "persona": str(persona.id),
        "archetype": str(Archetype.objects.get(name="Aliado").id),
        "scene_function": "carregador de malas",
        "traits": "simpático",
        "resistance": "nenhuma",
        "concession": "confirma o que viu",
        "presence": presence,
        "opening_order": str(order),
    }
    if decides:
        row["decides_outcome"] = "on"
    return row


def _formset(scenario: Scenario, extra_rows: list[dict]):
    factory = inlineformset_factory(
        Scenario,
        ScenarioRole,
        formset=ScenarioRoleFormSet,
        fields=[
            "persona",
            "archetype",
            "scene_function",
            "traits",
            "resistance",
            "concession",
            "presence",
            "decides_outcome",
            "opening_order",
        ],
        extra=0,
    )
    return factory(_formset_data(scenario, extra_rows), instance=scenario, prefix="roles")


@pytest.mark.django_db
def test_the_formset_accepts_a_supporting_third_role():
    hotel = Scenario.objects.get(slug="problema-no-quarto")
    porter = Persona.objects.create(name="Porter", voice="austin")

    formset = _formset(hotel, [_new_row(porter, SUPPORTING, 3)])

    assert formset.is_valid(), formset.non_form_errors()


@pytest.mark.django_db
def test_the_formset_refuses_a_third_principal():
    hotel = Scenario.objects.get(slug="problema-no-quarto")
    porter = Persona.objects.create(name="Porter", voice="austin")

    formset = _formset(hotel, [_new_row(porter, PRINCIPAL, 3)])

    assert not formset.is_valid()
    assert any("coadjuvante" in error for error in formset.non_form_errors())
