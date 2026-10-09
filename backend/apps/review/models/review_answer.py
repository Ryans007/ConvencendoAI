from django.db import models

from apps.review.models.review_item import ReviewItem
from apps.review.models.review_result import ReviewResult


class ReviewAnswer(models.Model):
    """Uma resposta falada do aluno numa etapa da revisão de um item.

    Cada tentativa julgada vira uma linha, com o que o sistema ouviu e o que o professor
    decidiu, para auditar se ele julgou bem. A etapa e a tentativa em que o item está são
    sempre calculadas a partir das respostas ainda sem resultado, nunca guardadas à parte.
    `result` fica vazio enquanto a revisão do item não terminou e aponta para o resultado
    quando ela termina.
    """

    item = models.ForeignKey(
        ReviewItem,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="item",
    )
    result = models.ForeignKey(
        ReviewResult,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answers",
        verbose_name="resultado",
        help_text="Vazio enquanto a revisão do item não terminou.",
    )
    step = models.PositiveSmallIntegerField(
        verbose_name="etapa",
        help_text="1 é falar a frase corrigida, 2 é falar uma frase nova com a mesma estrutura.",
    )
    attempt = models.PositiveSmallIntegerField(
        verbose_name="tentativa",
        help_text="1 ou 2: cada etapa aceita até duas tentativas.",
    )
    heard = models.TextField(
        verbose_name="ouvimos",
        help_text="A transcrição da fala do aluno.",
    )
    correct = models.BooleanField(
        verbose_name="certa",
        help_text="Se o professor considerou a resposta certa.",
    )
    feedback = models.TextField(
        verbose_name="feedback do professor",
        help_text="O feedback em português que o aluno viu.",
    )
    correction = models.TextField(
        blank=True,
        verbose_name="correção do professor",
        help_text="A frase do aluno corrigida, em inglês, quando a resposta estava errada.",
    )
    revealed_correct = models.TextField(
        blank=True,
        verbose_name="forma correta mostrada",
        help_text="A forma correta que a tela mostrou depois desta resposta, ou vazio.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="respondida em")

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "resposta da revisão"
        verbose_name_plural = "respostas da revisão"

    def __str__(self) -> str:
        return f"{self.item.rule}: etapa {self.step}, tentativa {self.attempt}"
