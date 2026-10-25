from django.db import models

from apps.catalog.constants import RolePresence
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
    quando ele trava — independente do arquétipo escolhido. `decides_outcome` marca o
    papel que tem poder de decidir o resultado da cena: só ele encerra a cena como
    resolvida e diz as falas finais. Um cenário sem nenhum papel marcado trata todos como
    quem decide.

    `presence` separa quem conduz a cena (principal) do terceiro personagem que só entra
    quando há motivo (coadjuvante), independente do arquétipo: um aliado pode ser principal,
    como o tech lead da negociação. `entry_cue` é a deixa de entrada do coadjuvante, o
    assunto ou momento em que ele entra; como `closing_hint` do cenário, é instrução
    dirigida ao modelo de linguagem e fica em inglês. As regras do elenco (no máximo três
    papéis, um coadjuvante que não decide nem abre a cena) ficam em `validators.py`.
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
    decides_outcome = models.BooleanField(
        default=False,
        verbose_name="decide o resultado da cena",
        help_text=(
            "Marque o papel que pode conceder o que o aluno quer e encerrar a cena. "
            "Um aliado, por exemplo, apoia o aluno mas não decide. Se nenhum papel do "
            "cenário estiver marcado, todos são tratados como quem decide."
        ),
    )
    presence = models.CharField(
        "presença na cena",
        max_length=20,
        choices=RolePresence.choices,
        default=RolePresence.PRINCIPAL,
        help_text=(
            "Principal conduz a conversa e reveza a vez com a outra principal. Coadjuvante "
            "só entra quando é chamado, quando o assunto é dele ou uma vez garantida na "
            "metade da cena; fala curto e nunca conduz. Um cenário tem no máximo um."
        ),
    )
    entry_cue = models.TextField(
        "deixa de entrada",
        blank=True,
        help_text=(
            "Só para o coadjuvante, em inglês: o assunto ou momento em que ele entra. "
            'Exemplo: "When the guest describes the problem with the new room".'
        ),
    )
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
