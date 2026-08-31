from django.db import models


class ModelPurpose(models.TextChoices):
    """Os dois papéis do núcleo conversacional que consomem um modelo de LLM."""

    PERSONA = "persona", "Personas"
    JUDGE = "judge", "Avaliador"
