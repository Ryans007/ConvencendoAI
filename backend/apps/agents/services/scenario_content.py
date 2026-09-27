from dataclasses import dataclass

from django.utils.text import slugify

from apps.catalog.models import Level, Scenario
from apps.catalog.services.criteria import applicable_criteria
from apps.catalog.validators import effective_scenario_level_weights


@dataclass(frozen=True)
class CriterionItem:
    """Um critério de aceite aplicável ao nível em que o cenário está sendo executado."""

    code: str
    text: str


@dataclass(frozen=True)
class Role:
    """Uma persona instanciada na cena, com o comportamento que o nível define para ela.

    `key` identifica o papel dentro do cenário (usado como `current_speaker` no estado
    do grafo, e citado no prompt da persona para dizer a quem ela pode passar a vez).
    """

    key: str
    name: str
    voice: str
    archetype: str
    scene_function: str
    traits: str
    resistance: str
    concession: str
    extra_instruction: str
    scaffolds: bool


@dataclass(frozen=True)
class ScenarioContent:
    """Conteúdo completo de uma execução: um cenário do catálogo, num nível específico.

    É o único ponto de acesso ao catálogo usado pelo grafo e pelo avaliador — nenhum
    dos dois consulta os models diretamente.
    """

    slug: str
    title: str
    objective: str
    context: str
    closing_hint: str
    max_turns: int
    difficulty_label: str
    expected_production: str
    expected_cefr: str
    language: str
    questions: str
    rephrasing: str
    concession_pace: str
    hints_policy: str
    weights: dict[str, int]
    roles: list[Role]
    criteria: list[CriterionItem]

    def role(self, key: str) -> Role:
        for role in self.roles:
            if role.key == key:
                return role
        raise KeyError(f"Role '{key}' is not part of scenario '{self.slug}'")

    def role_keys(self) -> list[str]:
        return [role.key for role in self.roles]


def load_scenario_content(scenario: Scenario, level: Level) -> ScenarioContent:
    """Monta o conteúdo de execução de um cenário para um nível, a partir do catálogo.

    Editar o cenário ou o nível no admin altera a próxima execução: nada aqui vem de
    uma fonte fixa fora do catálogo.
    """
    hint_override = scenario.level_hints.filter(level=level).first()
    closing_hint = (
        hint_override.closing_hint_override if hint_override else scenario.closing_hint
    )

    weight_overrides = {
        override.dimension: override.weight
        for override in scenario.level_weight_overrides.filter(level=level)
    }
    weights = effective_scenario_level_weights(level, weight_overrides)

    roles = [
        Role(
            key=slugify(scenario_role.persona.name),
            name=scenario_role.persona.name,
            voice=scenario_role.persona.voice,
            archetype=scenario_role.archetype.name,
            scene_function=scenario_role.scene_function,
            traits=scenario_role.traits,
            resistance=scenario_role.resistance,
            concession=scenario_role.concession,
            extra_instruction=scenario_role.extra_instruction,
            scaffolds=scenario_role.scaffolding_levels.filter(pk=level.pk).exists(),
        )
        for scenario_role in scenario.roles.select_related(
            "persona", "archetype"
        ).order_by("opening_order")
    ]

    criteria = [
        CriterionItem(code=criterion.code, text=criterion.text)
        for criterion in applicable_criteria(scenario, level)
    ]

    return ScenarioContent(
        slug=scenario.slug,
        title=scenario.title,
        objective=scenario.objective,
        context=scenario.context,
        closing_hint=closing_hint,
        max_turns=level.max_turns,
        difficulty_label=level.name,
        expected_production=level.expected_production,
        expected_cefr=level.expected_cefr,
        language=level.language,
        questions=level.questions,
        rephrasing=level.rephrasing,
        concession_pace=level.concession_pace,
        hints_policy=level.hints,
        weights=weights,
        roles=roles,
        criteria=criteria,
    )
