from django.db import models


class LoginFailure(models.Model):
    """Uma tentativa de login com senha errada, do app ou do admin.

    É a base do bloqueio por senhas erradas e, ao mesmo tempo, a auditoria de um ataque.
    Guarda o nome de usuário como foi digitado, mesmo que ele não exista, e o IP do cliente,
    e nunca a senha. As tentativas que o próprio bloqueio recusa não são gravadas, para o
    bloqueio não se renovar sozinho.
    """

    username = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="usuário informado",
        help_text="O nome de usuário como foi digitado, exista ou não.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP",
        help_text="O IP do cliente, já descontados os proxies confiáveis.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="quando")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["username", "created_at"], name="loginfail_user_created"),
            models.Index(fields=["ip_address", "created_at"], name="loginfail_ip_created"),
        ]
        verbose_name = "tentativa de login com erro"
        verbose_name_plural = "tentativas de login com erro"

    def __str__(self) -> str:
        return f"{self.username or '(vazio)'} · {self.ip_address or 'IP desconhecido'}"
