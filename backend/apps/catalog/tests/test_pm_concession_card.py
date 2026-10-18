import importlib

import pytest
from django.apps import apps

from apps.catalog.models import ScenarioRole

pytestmark = pytest.mark.django_db


_CARD_MIGRATION = importlib.import_module("apps.catalog.migrations.0020_deadline_pm_concession_card")


def _pm() -> ScenarioRole:
    return ScenarioRole.objects.get(scenario__slug="negociar-prazo", persona__name="Rachel")


def test_the_pm_card_lists_what_is_enough_to_concede():
    concession = _pm().concession

    assert "(1) o que causa o atraso" in concession
    assert "(2) o que entrega em cada data" in concession
    assert "Não pede mais detalhe técnico do que isso" in concession


def test_undoing_the_card_migration_restores_the_previous_text_and_redoing_rewrites_it():
    _CARD_MIGRATION.restore_card(apps, None)

    assert _pm().concession == _CARD_MIGRATION.OLD

    _CARD_MIGRATION.rewrite_card(apps, None)

    assert _pm().concession == _CARD_MIGRATION.NEW


def test_a_card_edited_by_the_admin_is_not_overwritten():
    ScenarioRole.objects.filter(pk=_pm().pk).update(concession="Texto do administrador.")

    _CARD_MIGRATION.rewrite_card(apps, None)
    assert _pm().concession == "Texto do administrador."

    _CARD_MIGRATION.restore_card(apps, None)
    assert _pm().concession == "Texto do administrador."
