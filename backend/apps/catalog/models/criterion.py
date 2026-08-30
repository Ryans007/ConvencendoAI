from django.db import models

from apps.catalog.models.level import Level
from apps.catalog.models.scenario import Scenario


class Criterion(models.Model):
    """Critério de aceite de um cenário, oculto do aluno até o relatório final.

    `text` descreve o critério para o avaliador e para o relatório: é conteúdo de
    domínio, como objetivo e contexto do cenário, e fica em português. `levels`
    declara em quais níveis o critério se aplica — no nível de compreensão, um
    critério que exige produção livre simplesmente não entra na avaliação.
    """

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="criteria")
    code = models.CharField(max_length=20)
    text = models.TextField()
    order = models.PositiveSmallIntegerField()
    levels = models.ManyToManyField(Level, related_name="criteria")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scenario", "code"], name="unique_scenario_criterion_code"
            ),
            models.UniqueConstraint(
                fields=["scenario", "order"], name="unique_scenario_criterion_order"
            ),
        ]
        ordering = ["scenario", "order"]

    def __str__(self) -> str:
        return f"{self.scenario} · {self.code}"
