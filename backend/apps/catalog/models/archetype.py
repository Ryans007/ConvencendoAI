from django.db import models


class Archetype(models.Model):
    """Papel interacional que uma persona pode exercer numa cena.

    Interpolado como texto no prompt da persona: um arquétipo novo funciona sem
    alteração de código, porque é o modelo de linguagem que o interpreta.
    """

    name = models.CharField(max_length=60, unique=True)
    description = models.TextField()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
