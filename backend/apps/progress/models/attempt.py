from django.conf import settings
from django.db import models

from apps.catalog.constants import RubricDimension
from apps.catalog.models import Level, Scenario
from apps.progress.choices import EndedBy


class Attempt(models.Model):
    """Uma sessão de um aluno num cenário e nível específicos.

    Chaveada pelos três porque um nível diferente do mesmo cenário é uma tarefa
    diferente: notas de níveis distintos não são comparáveis entre si. Nasce ao
    início da sessão, com `started_at`; os campos de resultado ficam vazios até o
    avaliador concluir, quando `completed_at` é preenchido.

    `hints_enabled` e `hints_used` registram o apoio que o aluno escolheu ter: a dica não
    entra na nota, mas a auditoria precisa ver quanto o aluno dependeu dela.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts"
    )
    scenario = models.ForeignKey(Scenario, on_delete=models.PROTECT, related_name="attempts")
    level = models.ForeignKey(Level, on_delete=models.PROTECT, related_name="attempts")
    final_score = models.PositiveSmallIntegerField(null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    memory_summary = models.TextField(blank=True)
    feedback = models.TextField(blank=True)
    hints_enabled = models.BooleanField(
        default=False,
        verbose_name="dicas ligadas",
        help_text="O aluno começou a sessão com as dicas ligadas.",
    )
    hints_used = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="dicas usadas",
        help_text="Quantas dicas o aluno pediu na sessão, no máximo uma por vez dele.",
    )
    ended_by = models.CharField(
        "encerrada por",
        max_length=20,
        choices=EndedBy.choices,
        blank=True,
        help_text="O motivo pelo qual a sessão foi encerrada.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.user} · {self.scenario} · {self.level}"


class ScoreBreakdown(models.Model):
    """Sub-nota de uma dimensão numa tentativa, com o peso que valia no momento.

    `weight_at_time` é o registro histórico: se o cenário for reajustado depois, esta
    linha continua explicando a nota exatamente como foi calculada. `comment` é a explicação
    da nota escrita pelo avaliador, para o relatório dizer ao aluno o porquê do número.
    """

    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE, related_name="score_breakdowns"
    )
    dimension = models.CharField(max_length=20, choices=RubricDimension.choices)
    value = models.PositiveSmallIntegerField()
    weight_at_time = models.PositiveSmallIntegerField()
    comment = models.TextField(
        blank=True,
        default="",
        verbose_name="comentário",
        help_text=(
            "Uma frase do avaliador, em português, que explica a nota ao aluno. Vazio na "
            "dimensão objetivo, que é calculada, e nas tentativas anteriores ao comentário."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "dimension"], name="unique_attempt_dimension"
            )
        ]
        ordering = ["attempt", "dimension"]

    def __str__(self) -> str:
        return f"{self.attempt} · {self.dimension} = {self.value}"


class AttemptCriterion(models.Model):
    """Critério avaliado numa tentativa, com o texto como estava redigido no momento.

    `text_at_time` é o mesmo tipo de registro histórico de `ScoreBreakdown`: reescrever
    o critério no catálogo depois não altera esta linha nem a nota que ela sustenta.
    """

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="criteria")
    code = models.CharField(max_length=20)
    text_at_time = models.TextField()
    met = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "code"], name="unique_attempt_criterion_code"
            )
        ]
        ordering = ["attempt", "code"]

    def __str__(self) -> str:
        return f"{self.attempt} · {self.code}"
