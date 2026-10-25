import dataclasses

from apps.agents.services.scenario_content import ScenarioContent, load_scenario_content
from apps.catalog.models import Level, Scenario

PORTER_CUE = "When the guest describes the problem with the new room"


def hotel_with_porter(level_order: int = 3, max_turns: int | None = None) -> ScenarioContent:
    """O cenário do hotel com um terceiro papel coadjuvante, o carregador Mike.

    Montado em memória sobre o cenário semeado, para testar o motor com três personagens
    sem depender de um cenário de três papéis no banco.
    """
    content = load_scenario_content(
        Scenario.objects.get(slug="problema-no-quarto"), Level.objects.get(order=level_order)
    )
    emma, james = content.roles
    porter = dataclasses.replace(
        james,
        key="mike",
        name="Mike",
        voice="austin",
        archetype="Aliado",
        decides_outcome=False,
        scene_function="carregador de malas",
        supporting=True,
        entry_cue=PORTER_CUE,
    )
    changes = {"roles": [emma, james, porter]}
    if max_turns is not None:
        changes["max_turns"] = max_turns
    return dataclasses.replace(content, **changes)
