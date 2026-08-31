from django.db import models


class LLMProvider(models.Model):
    """Provedor de LLM com API compatível com a da OpenAI.

    `code` é texto livre, não enum: um provedor novo não exige alteração de código,
    só um cadastro.
    """

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    base_url = models.URLField()
    api_key = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
