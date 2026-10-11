from django.conf import settings
from django.db import models


class LiveSessionLease(models.Model):
    """Uma sessão de voz aberta de um aluno, para limitar quantas ele tem ao mesmo tempo.

    Nasce quando a conexão da sessão é aceita e some quando ela termina. `expires_at` existe
    para uma queda do servidor, que apaga a conexão sem passar pelo fim normal, não prender o
    aluno: uma concessão vencida deixa de contar e é apagada na próxima abertura. Fica no banco
    e não no cache, porque o projeto não tem cache compartilhado e cada worker do servidor teria
    a sua contagem.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="live_session_leases",
        verbose_name="aluno",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="aberta em")
    expires_at = models.DateTimeField(
        verbose_name="vale até",
        help_text="Depois disso a sessão deixa de contar como aberta, mesmo sem ter terminado.",
    )

    class Meta:
        indexes = [models.Index(fields=["user", "expires_at"], name="lease_user_expires")]
        verbose_name = "sessão de voz aberta"
        verbose_name_plural = "sessões de voz abertas"

    def __str__(self) -> str:
        return f"{self.user} · até {self.expires_at:%H:%M}"
