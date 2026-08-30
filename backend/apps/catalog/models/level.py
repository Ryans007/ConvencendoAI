from django.db import models

from apps.catalog.constants import RubricDimension


class HintPolicy(models.TextChoices):
    """Política de exibição de dicas de contexto na tela durante a sessão."""

    ALWAYS = "always", "Sempre"
    WHEN_STUCK = "when_stuck", "Quando o aluno travar"
    NEVER = "never", "Nunca"


class Level(models.Model):
    """Um dos três níveis de dificuldade: eixo único de produção esperada do aluno e de
    comportamento da persona, os dois acoplados por construção, não por escolha
    independente.

    `language`, `questions`, `rephrasing` e `concession_pace` são instrução dirigida ao
    modelo de linguagem e ficam em inglês, porque compõem o prompt da persona. Os demais
    campos de texto do catálogo — objetivo, contexto, critério, traço — descrevem a cena
    para o aluno e ficam em português.
    """

    order = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=60)
    expected_production = models.CharField(max_length=120)
    language = models.TextField()
    questions = models.TextField()
    rephrasing = models.TextField()
    concession_pace = models.TextField()
    scaffolding_enabled = models.BooleanField(default=False)
    hints = models.CharField(max_length=20, choices=HintPolicy.choices)
    max_turns = models.PositiveSmallIntegerField()
    expected_cefr = models.CharField(max_length=20)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.order} — {self.name}"


class LevelDefaultWeight(models.Model):
    """Peso padrão de uma dimensão da rúbrica num nível.

    A soma das sete linhas de um mesmo nível deve ser 100 — ver
    `apps.catalog.validators.clean_level_weights`, chamado pelo formulário do admin
    sobre o conjunto inteiro, porque a validação depende dos irmãos, não só desta linha.
    """

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="default_weights")
    dimension = models.CharField(max_length=20, choices=RubricDimension.choices)
    weight = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["level", "dimension"], name="unique_level_dimension_weight"
            )
        ]
        ordering = ["level", "dimension"]

    def __str__(self) -> str:
        return f"{self.level} · {self.dimension} = {self.weight}"
