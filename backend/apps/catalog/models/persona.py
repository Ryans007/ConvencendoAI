from django.db import models


class Persona(models.Model):
    """Identidade persistente do elenco, independente de cenário.

    Reaparece com o mesmo nome e a mesma voz em cenários diferentes da mesma trilha —
    é o que dá continuidade ao arco narrativo mesmo quando o papel dela muda de cena
    para cena (ver `ScenarioRole`).
    """

    name = models.CharField(max_length=60)
    voice = models.CharField(max_length=40)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
