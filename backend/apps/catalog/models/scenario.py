from django.db import models

from apps.catalog.models.track import Track


class Scenario(models.Model):
    """Uma tarefa dentro de uma trilha, com objetivo verificável e critérios ocultos.

    `closing_hint` é a oportunidade que a cena precisa criar antes de encerrar, para
    que os critérios de aceite sejam alcançáveis. Como os campos comportamentais de
    `Level`, é instrução dirigida ao modelo de linguagem e fica em inglês.
    """

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="scenarios")
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField()
    objective = models.TextField()
    context = models.TextField()
    closing_hint = models.TextField()
    cooldown_hours = models.PositiveSmallIntegerField(default=12)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["track", "order"], name="unique_track_order"),
        ]
        ordering = ["track", "order"]

    def __str__(self) -> str:
        return self.title
