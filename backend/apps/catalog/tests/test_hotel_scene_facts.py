import importlib

import pytest
from django.apps import apps

from apps.catalog.models import ScenarioRole

pytestmark = pytest.mark.django_db

_MIGRATION = importlib.import_module("apps.catalog.migrations.0015_seed_hotel_scene_facts")


def _hotel_roles():
    return ScenarioRole.objects.filter(
        scenario__slug="problema-no-quarto", persona__name__in=["Emma", "James"]
    )


def _role(name: str) -> ScenarioRole:
    return _hotel_roles().get(persona__name=name)


def test_both_hotel_roles_get_the_same_facts():
    texts = {role.extra_instruction for role in _hotel_roles()}

    assert texts == {_MIGRATION.HOTEL_FACTS}
    assert _hotel_roles().count() == 2


def test_the_facts_say_what_the_hotel_does_not_offer():
    facts = _MIGRATION.HOTEL_FACTS

    assert "não oferece reembolso nem desconto" in facts
    assert "conserta o ar-condicionado hoje" in facts
    assert "sem nenhum custo extra" in facts
    assert "sair e voltar" in facts


def test_a_role_that_already_had_a_text_is_not_overwritten():
    handwritten = "Texto escrito pelo administrador."
    ScenarioRole.objects.filter(pk=_role("Emma").pk).update(extra_instruction=handwritten)
    ScenarioRole.objects.filter(pk=_role("James").pk).update(extra_instruction="")

    _MIGRATION.seed_hotel_scene_facts(apps, None)

    assert _role("Emma").extra_instruction == handwritten
    assert _role("James").extra_instruction == _MIGRATION.HOTEL_FACTS


def test_undoing_clears_both_roles():
    _MIGRATION.clear_hotel_scene_facts(apps, None)

    assert {role.extra_instruction for role in _hotel_roles()} == {""}


def test_undoing_does_not_touch_a_different_text():
    handwritten = "Texto escrito pelo administrador."
    ScenarioRole.objects.filter(pk=_role("Emma").pk).update(extra_instruction=handwritten)

    _MIGRATION.clear_hotel_scene_facts(apps, None)

    assert _role("Emma").extra_instruction == handwritten
    assert _role("James").extra_instruction == ""


def test_applying_twice_changes_nothing():
    _MIGRATION.seed_hotel_scene_facts(apps, None)

    assert {role.extra_instruction for role in _hotel_roles()} == {_MIGRATION.HOTEL_FACTS}
