from django.db import models

from apps.catalog.models.archetype import Archetype
from apps.catalog.models.level import Level
from apps.catalog.models.persona import Persona
from apps.catalog.models.scenario import Scenario


class ScenarioRole(models.Model):
    """O que uma persona é dentro de um cenário específico.

    Separa identidade (`Persona`) de instanciação (`ScenarioRole`) porque a mesma
    persona exerce papéis diferentes em cenários diferentes da mesma trilha — a
    recrutadora de RH de um cenário pode ser a gerente de produto do seguinte.

    `scene_function`, `traits`, `resistance`, `concession` e `extra_instruction`
    descrevem a persona para a cena, como o objetivo e o contexto do cenário: ficam em
    português. `scaffolding_levels` marca em quais níveis este papel apoia o aluno
    quando ele trava — independente do arquétipo escolhido.
    """

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="roles")
    persona = models.ForeignKey(
        Persona, on_delete=models.CASCADE, related_name="scenario_roles"
    )
    archetype = models.ForeignKey(
        Archetype, on_delete=models.PROTECT, related_name="scenario_roles"
    )
    scene_function = models.CharField(max_length=120)
    traits = models.TextField()
    resistance = models.TextField()
    concession = models.TextField()
    extra_instruction = models.TextField(blank=True)
    opening_order = models.PositiveSmallIntegerField()
    scaffolding_levels = models.ManyToManyField(
        Level, blank=True, related_name="scaffolding_roles"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scenario", "persona"], name="unique_scenario_persona"
            ),
            models.UniqueConstraint(
                fields=["scenario", "opening_order"], name="unique_scenario_opening_order"
            ),
        ]
        ordering = ["scenario", "opening_order"]

    def __str__(self) -> str:
        return f"{self.persona} em {self.scenario}"
