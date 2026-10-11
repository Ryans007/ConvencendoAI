import os

from django.core.validators import RegexValidator
from django.db import models

_ENV_NAME = RegexValidator(
    r"^[A-Z][A-Z0-9_]*$",
    "Use só letras maiúsculas, números e sublinhado, começando por letra (ex.: GROQ_API_KEY).",
)


class LLMProvider(models.Model):
    """Provedor de LLM com API compatível com a da OpenAI.

    `code` é texto livre, não enum: um provedor novo não exige alteração de código,
    só um cadastro.

    A chave de acesso nunca é gravada: o banco guarda só o nome da variável de ambiente
    (`api_key_env`), e `api_key` a lê do ambiente do servidor a cada uso. Assim um backup do
    banco, o admin e uma captura de tela não expõem a chave, e trocá-la é trocar o ambiente.
    """

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    base_url = models.URLField()
    api_key_env = models.CharField(
        max_length=80,
        validators=[_ENV_NAME],
        verbose_name="variável de ambiente da chave",
        help_text=(
            "O nome da variável de ambiente que guarda a chave de acesso deste provedor, como "
            "GROQ_API_KEY. A chave em si fica só no ambiente do servidor, nunca aqui."
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def api_key(self) -> str:
        """A chave lida do ambiente do servidor, ou vazio se a variável não está definida."""
        return os.environ.get(self.api_key_env, "").strip()

    @property
    def has_api_key(self) -> bool:
        """A variável de ambiente da chave está definida e não vazia."""
        return bool(self.api_key)
