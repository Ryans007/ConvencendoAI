from django.conf import settings
from django.db import models

from apps.usage.constants import UsagePurpose


class ModelUsage(models.Model):
    """O uso de uma chamada do sistema a um modelo de IA: dono, consumo e custo.

    Uma linha por chamada do sistema, e não por resposta do provedor: quando o modelo
    responde mais de uma vez, por exemplo numa nova tentativa por saída fora do schema, a
    linha soma o consumo de todas e `model_calls` diz quantas foram. O custo fica gravado com
    o preço do momento, no mesmo espírito do peso gravado em cada nota: mudar o preço do
    modelo depois não reescreve o passado.

    O aluno, a tentativa, o item de revisão e o modelo são referências que se desfazem para
    vazio ao apagar o registro original, e o nome do aluno e o identificador do modelo ficam
    copiados na linha, para a auditoria do gasto sobreviver à limpeza. Sem aluno, a linha é uso
    do sistema: comandos e medições pelo shell.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_usages",
        verbose_name="aluno",
        help_text="Vazio quando a chamada não veio de um aluno: uso do sistema.",
    )
    username_at_time = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="nome do aluno na época",
        help_text="Cópia do nome de usuário no momento da chamada.",
    )
    attempt = models.ForeignKey(
        "progress.Attempt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_usages",
        verbose_name="sessão",
    )
    review_item = models.ForeignKey(
        "review.ReviewItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_usages",
        verbose_name="item de revisão",
    )
    purpose = models.CharField(
        max_length=20, choices=UsagePurpose.choices, verbose_name="papel"
    )
    llm_model = models.ForeignKey(
        "llm.LLMModel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usages",
        verbose_name="modelo",
    )
    model_id_at_time = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="identificador do modelo na época",
    )
    input_tokens = models.PositiveIntegerField(default=0, verbose_name="tokens de entrada")
    output_tokens = models.PositiveIntegerField(
        default=0,
        verbose_name="tokens de saída",
        help_text="Inclui o raciocínio do modelo.",
    )
    model_calls = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="respostas do modelo",
        help_text="Quantas respostas do provedor a chamada do sistema consumiu.",
    )
    audio_seconds = models.FloatField(
        null=True,
        blank=True,
        verbose_name="segundos de áudio",
        help_text="Duração real do áudio transcrito, quando o provedor a informou.",
    )
    billed_audio_seconds = models.FloatField(
        null=True,
        blank=True,
        verbose_name="segundos cobrados",
        help_text="A duração do áudio com o mínimo por pedido do provedor.",
    )
    characters = models.PositiveIntegerField(
        default=0, verbose_name="caracteres sintetizados"
    )
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="duração (ms)")
    failed = models.BooleanField(default=False, verbose_name="falhou")
    error_code = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="tipo do erro",
        help_text="O tipo da exceção, quando a chamada falhou.",
    )
    cost_usd = models.DecimalField(
        max_digits=14,
        decimal_places=8,
        default=0,
        verbose_name="custo estimado (US$)",
        help_text="Calculado com o preço do modelo no momento da chamada.",
    )
    priced = models.BooleanField(
        default=False,
        verbose_name="com preço",
        help_text="Falso quando o modelo não tinha preço cadastrado: o custo é desconhecido.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="quando")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "created_at"], name="usage_user_created"),
            models.Index(fields=["created_at"], name="usage_created"),
        ]
        verbose_name = "uso de modelo"
        verbose_name_plural = "uso de modelos"

    def __str__(self) -> str:
        who = self.username_at_time or "sistema"
        return f"{who} · {self.get_purpose_display()} · {self.model_id_at_time}"
