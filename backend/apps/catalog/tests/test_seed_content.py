import importlib

import pytest
from django.apps import apps

from apps.catalog.models import (
    Archetype,
    Criterion,
    Level,
    Persona,
    Scenario,
    ScenarioLevelHint,
    Track,
)


def _seed_function(module_name: str, function_name: str):
    module = importlib.import_module(f"apps.catalog.migrations.{module_name}")
    return getattr(module, function_name)


@pytest.mark.django_db
def test_aplicar_a_carga_duas_vezes_nao_duplica_nenhum_registro() -> None:
    """Reexecutar as migrations de conteúdo inicial não duplica nenhum registro.

    A carga já foi aplicada uma vez por `migrate` ao construir o banco de teste;
    chamar as mesmas funções aqui de novo é a segunda aplicação.
    """
    seed_levels = _seed_function("0005_seed_archetypes_and_levels", "seed_archetypes_and_levels")
    seed_tracks = _seed_function("0006_seed_validated_tracks", "seed_validated_tracks")
    seed_criteria = _seed_function("0007_seed_criteria", "seed_criteria")
    seed_closing_hint = _seed_function(
        "0008_seed_interview_level_one_closing_hint", "seed_interview_level_one_closing_hint"
    )

    seed_levels(apps, None)
    seed_tracks(apps, None)
    seed_criteria(apps, None)
    seed_closing_hint(apps, None)

    assert Archetype.objects.count() == 6
    assert Level.objects.count() == 3
    assert Track.objects.count() == 2
    assert Persona.objects.count() == 4
    assert Scenario.objects.count() == 3
    assert Criterion.objects.count() == 15
    assert ScenarioLevelHint.objects.count() == 1


@pytest.mark.django_db
def test_nivel_1_da_entrevista_fecha_com_pergunta_fechada() -> None:
    """O nível 1 da entrevista usa a dica de fechamento própria, não a do cenário."""
    hint = ScenarioLevelHint.objects.get(
        scenario__slug="entrevista-de-emprego", level__order=1
    )
    assert "yes or no" in hint.closing_hint_override


@pytest.mark.django_db
def test_todo_par_de_cenario_e_nivel_semeado_tem_criterio_aplicavel() -> None:
    """Cada um dos nove pares de cenário e nível semeados tem ao menos um critério."""
    for scenario in Scenario.objects.all():
        for level in Level.objects.all():
            assert scenario.criteria.filter(
                levels=level
            ).exists(), f"{scenario.slug} nível {level.order} sem critério aplicável"
