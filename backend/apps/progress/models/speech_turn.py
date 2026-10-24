from django.db import models

from apps.progress.models.attempt import Attempt


class SpeechTurn(models.Model):
    """Uma vez de fala do aluno numa sessão de voz, com o tempo e as palavras que o STT ouviu.

    É a matéria-prima das medidas de fluência e vocabulário. As medidas da sessão (mediana de
    reação, velocidade, pausas, diversidade e alcance) não são gravadas: são calculadas destas
    linhas sempre que preciso, na avaliação e no relatório, para nunca divergirem das vezes que as
    geraram. O texto fica guardado para a auditoria conseguir refazer qualquer conta.
    """

    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name="speech_turns",
        verbose_name="tentativa",
    )
    order = models.PositiveSmallIntegerField(
        verbose_name="ordem",
        help_text="A posição desta vez entre as vezes de fala do aluno na sessão, a partir de 1.",
    )
    waited_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="espera (ms)",
        help_text=(
            "Tempo entre o fim da fala do personagem e o início da gravação, medido pelo "
            "navegador. Vazio quando o navegador não informou ou informou um valor inválido."
        ),
    )
    leading_silence_ms = models.PositiveIntegerField(
        verbose_name="silêncio inicial (ms)",
        help_text="Tempo entre o início da gravação e o começo da primeira palavra.",
    )
    speech_ms = models.PositiveIntegerField(
        verbose_name="tempo de fala (ms)",
        help_text="Tempo entre o começo da primeira palavra e o fim da última.",
    )
    word_count = models.PositiveSmallIntegerField(
        verbose_name="palavras",
        help_text="Quantas palavras o STT ouviu nesta vez.",
    )
    long_pauses = models.PositiveSmallIntegerField(
        verbose_name="pausas longas",
        help_text="Intervalos de mais de 1,5 segundo entre duas palavras seguidas desta vez.",
    )
    after_hint = models.BooleanField(
        default=False,
        verbose_name="depois de dica",
        help_text="O aluno tinha visto uma dica nesta vez; ela fica fora da medida de reação.",
    )
    text = models.TextField(
        verbose_name="texto",
        help_text="O que o STT ouviu nesta vez.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="registrada em")

    class Meta:
        verbose_name = "vez de fala"
        verbose_name_plural = "vezes de fala"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "order"], name="unique_attempt_speech_turn")
        ]
        ordering = ["attempt", "order"]

    def __str__(self) -> str:
        return f"{self.attempt} · vez {self.order}"
