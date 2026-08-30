import pytest

from apps.catalog.models import Criterion, Level, Scenario, Track
from apps.catalog.services import applicable_criteria


@pytest.fixture
def track(db) -> Track:
    return Track.objects.create(
        slug="viagem-teste",
        title="Viagem e Intercâmbio (teste)",
        order=900,
        student_role="hóspede de um hotel em Londres",
    )


@pytest.fixture
def scenario(track: Track) -> Scenario:
    return Scenario.objects.create(
        track=track,
        slug="hotel",
        title="Problema no quarto",
        order=1,
        objective="objetivo",
        context="contexto",
        closing_hint="Wrap up the scene.",
    )


@pytest.fixture
def levels(db) -> dict[int, Level]:
    return {n: Level.objects.get(order=n) for n in (1, 2, 3)}


def test_criterio_de_producao_nao_aparece_no_nivel_de_compreensao(
    scenario: Scenario, levels: dict[int, Level]
) -> None:
    """Um critério declarado só nos níveis 2 e 3 não é devolvido para o nível 1."""
    criterion = Criterion.objects.create(
        scenario=scenario, code="c1", text="Explicou o motivo técnico do atraso", order=1
    )
    criterion.levels.set([levels[2], levels[3]])

    assert list(applicable_criteria(scenario, levels[1])) == []
    assert list(applicable_criteria(scenario, levels[2])) == [criterion]
    assert list(applicable_criteria(scenario, levels[3])) == [criterion]


def test_criterio_comum_aparece_em_qualquer_nivel(
    scenario: Scenario, levels: dict[int, Level]
) -> None:
    """Um critério declarado nos três níveis é devolvido em qualquer um deles."""
    criterion = Criterion.objects.create(
        scenario=scenario, code="c1", text="Manteve um tom cordial durante toda a conversa", order=1
    )
    criterion.levels.set(levels.values())

    for level in levels.values():
        assert list(applicable_criteria(scenario, level)) == [criterion]
