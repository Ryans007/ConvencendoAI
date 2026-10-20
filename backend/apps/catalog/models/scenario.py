from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models.track import Track


class Scenario(models.Model):
    """Uma tarefa dentro de uma trilha, com objetivo verificável e critérios ocultos.

    `closing_hint` é a oportunidade que a cena precisa criar antes de encerrar, para
    que os critérios de aceite sejam alcançáveis. Como os campos comportamentais de
    `Level`, é instrução dirigida ao modelo de linguagem e fica em inglês.

    `max_consecutive_turns` limita quantas rodadas seguidas a mesma persona conduz: o
    modelo, sozinho, não divide a conversa, e cada cena tem o próprio ritmo.

    `max_turns` limita o número total de rodadas permitidas na cena.
    """

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="scenarios")
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField()
    objective = models.TextField()
    context = models.TextField()
    closing_hint = models.TextField()
    cooldown_hours = models.PositiveSmallIntegerField(default=12)
    max_consecutive_turns = models.PositiveSmallIntegerField(
        "máximo de rodadas seguidas da mesma persona",
        default=3,
        validators=[MinValueValidator(1)],
        help_text=(
            "A cada rodada é sorteado um limite entre 2 e este valor; ao atingi-lo, a vez "
            "passa ao outro personagem. Nenhuma persona conduz mais rodadas seguidas que isto."
        ),
    )
    max_turns = models.PositiveSmallIntegerField(
        "máximo de turnos",
        null=True,
        blank=True,
        validators=[MinValueValidator(7)],
        help_text="Número máximo de turnos permitidos na cena.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["track", "order"], name="unique_track_order"),
        ]
        ordering = ["track", "order"]

    def __str__(self) -> str:
        return self.title
