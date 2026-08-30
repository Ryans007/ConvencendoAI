from django.db import models

from apps.catalog.constants import RubricDimension
from apps.catalog.models.level import Level
from apps.catalog.models.scenario import Scenario


class ScenarioLevelWeightOverride(models.Model):
    """Peso de uma dimensão sobrescrito por um cenário, para um nível específico.

    FK direta a cenário e nível, sem tabela intermediária de agrupamento — o mesmo
    padrão plano de `LevelDefaultWeight`. Cadastrar um cenário com peso sobrescrito
    cabe assim numa única tela do admin, sem exigir dois níveis de aninhamento.
    """

    scenario = models.ForeignKey(
        Scenario, on_delete=models.CASCADE, related_name="level_weight_overrides"
    )
    level = models.ForeignKey(
        Level, on_delete=models.CASCADE, related_name="scenario_weight_overrides"
    )
    dimension = models.CharField(max_length=20, choices=RubricDimension.choices)
    weight = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scenario", "level", "dimension"],
                name="unique_scenario_level_dimension_override",
            )
        ]
        ordering = ["scenario", "level", "dimension"]

    def __str__(self) -> str:
        return f"{self.scenario} · {self.level} · {self.dimension} = {self.weight}"
