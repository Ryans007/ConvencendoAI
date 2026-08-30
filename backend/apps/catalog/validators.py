from django.core.exceptions import ValidationError

from apps.catalog.constants import RubricDimension
from apps.catalog.models.level import Level

RUBRIC_TOTAL = 100


def validate_dimension_weights(weights: dict[str, int]) -> None:
    """Garante que os pesos efetivos das sete dimensões somam `RUBRIC_TOTAL`.

    `weights` deve conter uma entrada por dimensão da rúbrica: o chamador já resolveu
    a herança entre o padrão do nível e a sobreposição do cenário antes de chamar esta
    função.
    """
    missing = set(RubricDimension.values) - weights.keys()
    if missing:
        raise ValidationError(f"Faltam pesos para: {', '.join(sorted(missing))}.")

    total = sum(weights.values())
    if total != RUBRIC_TOTAL:
        raise ValidationError(f"A soma dos pesos deve ser {RUBRIC_TOTAL}, mas é {total}.")


def clean_level_weights(level: Level, weights_by_dimension: dict[str, int]) -> None:
    """Valida o conjunto completo de pesos padrão de um nível antes de salvar.

    Função pura, sem efeito colateral: recebe o mapeamento já montado pelo chamador
    (tipicamente o formset do admin) em vez de consultar o banco, para ser testável sem
    fixture e reutilizável fora do admin quando a API existir.
    """
    try:
        validate_dimension_weights(weights_by_dimension)
    except ValidationError as exc:
        raise ValidationError(f"Pesos inválidos para o nível '{level}': {exc.message}") from exc


def effective_scenario_level_weights(level: Level, overrides: dict[str, int]) -> dict[str, int]:
    """Combina os pesos padrão do nível com a sobreposição parcial de um cenário.

    As dimensões presentes em `overrides` substituem o padrão; as demais herdam do
    nível — a semântica de herança parcial descrita na decisão de projeto sobre pesos.
    """
    defaults = {w.dimension: w.weight for w in level.default_weights.all()}
    return {**defaults, **overrides}


def clean_scenario_level_weights(level: Level, overrides: dict[str, int]) -> None:
    """Valida que os pesos efetivos de um ajuste por cenário e nível somam `RUBRIC_TOTAL`.

    Função pura: recebe o nível e as sobreposições já montadas pelo chamador, sem
    consultar `ScenarioLevelWeightOverride` diretamente, para ser testável sem fixture.
    """
    effective = effective_scenario_level_weights(level, overrides)
    try:
        validate_dimension_weights(effective)
    except ValidationError as exc:
        raise ValidationError(
            f"Pesos inválidos para o ajuste no nível '{level}': {exc.message}"
        ) from exc
