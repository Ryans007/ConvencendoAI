from django.db import models

from apps.llm.key_box import open_sealed, seal

_HINT_MAX_CHARS = 6
_HINT_MASK = "••••••••"


class LLMProvider(models.Model):
    """Provedor de LLM com API compatível com a da OpenAI.

    `code` é texto livre, não enum: um provedor novo não exige alteração de código,
    só um cadastro.

    A chave de acesso é cadastrada no admin e gravada criptografada (`api_key_encrypted`), com
    uma chave derivada do `SECRET_KEY`. Assim um backup do banco sozinho não expõe a chave, e o
    admin só mostra o começo dela (`api_key_hint`). `api_key` decifra a chave a cada uso, e
    atribuir a `api_key` a criptografa.
    """

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    base_url = models.URLField()
    api_key_encrypted = models.TextField(blank=True, default="", editable=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def api_key(self) -> str:
        """A chave decifrada, ou vazio se não há chave ou se ela não decifra."""
        return open_sealed(self.api_key_encrypted).strip()

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.api_key_encrypted = seal((value or "").strip())

    @property
    def has_api_key(self) -> bool:
        """O provedor tem uma chave legível e não vazia."""
        return bool(self.api_key)

    @property
    def api_key_hint(self) -> str:
        """O começo da chave seguido de uma máscara, ou vazio se não há chave.

        Mostra no máximo 6 caracteres e nunca mais que um quarto da chave, para que uma chave
        curta não fique quase toda à vista. A máscara tem tamanho fixo, para não revelar o
        comprimento da chave.
        """
        key = self.api_key
        if not key:
            return ""
        return key[: min(_HINT_MAX_CHARS, len(key) // 4)] + _HINT_MASK
