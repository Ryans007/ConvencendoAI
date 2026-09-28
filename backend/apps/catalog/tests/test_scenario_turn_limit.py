import pytest
from django.core.exceptions import ValidationError
from django.utils import translation

from apps.catalog.models import Scenario, Track

pytestmark = pytest.mark.django_db


def _scenario(**overrides) -> Scenario:
    track = Track.objects.first()
    fields = {
        "track": track,
        "slug": "cenario-teste",
        "title": "Cenário de teste",
        "order": 99,
        "objective": "Objetivo.",
        "context": "Contexto.",
        "closing_hint": "Close the scene.",
    }
    return Scenario(**{**fields, **overrides})


def test_new_scenario_gets_the_default_maximum():
    assert _scenario().max_consecutive_turns == 3


def test_maximum_below_one_is_rejected_in_portuguese():
    with translation.override("pt-br"), pytest.raises(ValidationError) as error:
        _scenario(max_consecutive_turns=0).full_clean()

    messages = error.value.message_dict["max_consecutive_turns"]
    assert any("maior ou igual a 1" in message for message in messages)
