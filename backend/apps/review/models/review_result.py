from django.db import models

from apps.review.models.review_item import ReviewItem


class ReviewResultKind(models.TextChoices):
    """Como terminou uma revisão de um item."""

    FIRST_TRY = "first_try", "Acertou de primeira"
    SECOND_TRY = "second_try", "Acertou na segunda tentativa"
    FAILED = "failed", "Errou"
    DISCARDED = "discarded", "Descartado"


class ReviewResult(models.Model):
    """O que uma revisão terminada fez com um item: o resultado e o antes e depois da caixa.

    É o histórico de calendário do item. Quando o item é descartado, a caixa não muda e não
    há novo vencimento. As respostas que levaram a este resultado apontam para ele.
    """

    item = models.ForeignKey(
        ReviewItem,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="item",
    )
    outcome = models.CharField(
        max_length=12,
        choices=ReviewResultKind.choices,
        verbose_name="resultado",
    )
    box_before = models.PositiveSmallIntegerField(
        verbose_name="caixa antes",
        help_text="Índice da caixa do item antes desta revisão.",
    )
    box_after = models.PositiveSmallIntegerField(
        verbose_name="caixa depois",
        help_text="Índice da caixa do item depois desta revisão.",
    )
    due_on_after = models.DateField(
        null=True,
        blank=True,
        verbose_name="vence em",
        help_text="Novo vencimento do item, ou vazio quando foi descartado.",
    )
    finished_at = models.DateTimeField(auto_now_add=True, verbose_name="terminada em")

    class Meta:
        ordering = ["-finished_at", "-id"]
        verbose_name = "resultado da revisão"
        verbose_name_plural = "resultados da revisão"

    def __str__(self) -> str:
        return f"{self.item.rule}: {self.get_outcome_display()}"
