from django.db import models

from apps.catalog.models.level import Level
from apps.catalog.models.scenario import Scenario


class ScenarioLevelHint(models.Model):
    """Sobreposição do texto de fechamento (`Scenario.closing_hint`) para um nível
    específico.

    Necessário porque a oportunidade que a cena precisa criar antes de encerrar muda
    conforme o que o aluno consegue produzir em cada nível: uma pista escrita para
    conversa livre não funciona num nível de sim ou não.
    """

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="level_hints")
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="scenario_hints")
    closing_hint_override = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scenario", "level"], name="unique_scenario_level_hint"
            )
        ]
        ordering = ["scenario", "level"]

    def __str__(self) -> str:
        return f"{self.scenario} · {self.level}"
