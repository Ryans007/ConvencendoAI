from django.core.validators import MinValueValidator
from django.db import models

_AT_LEAST_ONE = [MinValueValidator(1)]


class AccessLimits(models.Model):
    """Os limites de acesso e de uso do sistema, configuráveis pelo superuser no admin.

    Linha única no sistema inteiro, como a configuração de modelos: `save()` força a chave
    primária e `get_solo()` é o ponto de leitura. Os limites protegem o login contra força
    bruta e o gasto com os provedores de IA contra o uso sem teto. O valor é lido a cada
    checagem, então uma mudança vale a partir do pedido seguinte, sem reiniciar o servidor.
    """

    login_max_failures_per_user = models.PositiveSmallIntegerField(
        default=5,
        validators=_AT_LEAST_ONE,
        verbose_name="senhas erradas por usuário",
        help_text=(
            "Quantas senhas erradas para o mesmo usuário, dentro da janela, bloqueiam o usuário."
        ),
    )
    login_max_failures_per_ip = models.PositiveSmallIntegerField(
        default=20,
        validators=_AT_LEAST_ONE,
        verbose_name="senhas erradas por IP",
        help_text="Quantas senhas erradas vindas do mesmo IP, dentro da janela, bloqueiam o IP.",
    )
    login_window_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=_AT_LEAST_ONE,
        verbose_name="janela das senhas erradas (min)",
        help_text="Por quantos minutos uma senha errada conta para o bloqueio.",
    )
    login_lockout_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=_AT_LEAST_ONE,
        verbose_name="tempo de bloqueio (min)",
        help_text="Quanto dura o bloqueio do usuário ou do IP depois do limite.",
    )
    max_open_voice_sessions = models.PositiveSmallIntegerField(
        default=1,
        validators=_AT_LEAST_ONE,
        verbose_name="sessões de voz abertas por aluno",
        help_text="Quantas sessões de voz um aluno pode ter abertas ao mesmo tempo.",
    )
    max_voice_sessions_per_day = models.PositiveSmallIntegerField(
        default=20,
        validators=_AT_LEAST_ONE,
        verbose_name="sessões de voz por dia",
        help_text="Quantas sessões de voz um aluno pode iniciar por dia.",
    )
    max_turn_audio_kb = models.PositiveIntegerField(
        default=2048,
        validators=_AT_LEAST_ONE,
        verbose_name="tamanho máximo do áudio de um turno (KB)",
        help_text="Áudios de turno maiores que isto são recusados sem serem transcritos.",
    )
    max_review_calls_per_minute = models.PositiveSmallIntegerField(
        default=20,
        validators=_AT_LEAST_ONE,
        verbose_name="chamadas da revisão por minuto",
        help_text="Quantas chamadas a modelos um aluno pode fazer pela revisão por minuto.",
    )

    class Meta:
        verbose_name = "limites de acesso e uso"
        verbose_name_plural = "limites de acesso e uso"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        raise RuntimeError("AccessLimits é singleton: não pode ser removido.")

    @classmethod
    def get_solo(cls) -> "AccessLimits":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return "Limites de acesso e uso"
