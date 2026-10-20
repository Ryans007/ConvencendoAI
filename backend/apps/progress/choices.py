from django.db import models


class EndedBy(models.TextChoices):
    """Como uma sessão terminou: no limite de turnos da cena ou a pedido do aluno."""

    TURN_LIMIT = "turn_limit", "Limite de turnos"
    STUDENT = "student", "pedido do aluno"
