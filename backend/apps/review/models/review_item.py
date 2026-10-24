from django.conf import settings
from django.db import models

from apps.progress.models import Attempt


class ReviewItem(models.Model):
    """Uma regra de inglês que o aluno errou e precisa revisar.

    O que se revisa é a regra, e não o trecho: "I have worked there yesterday" e "I have
    finished the API last week" são o mesmo item, a regra do passado simples com tempo já
    terminado. Cada vez que o aluno erra nela vira uma `ReviewOccurrence`, e a mais recente
    é o exemplo que o cartão mostra.

    `box` é o índice da caixa de intervalo e `due_on`, o dia em que o item volta. "Dominado"
    não é um campo: é estar numa caixa alta, calculado por `apps.review.services.schedule`,
    para nenhum estado de progresso ficar guardado em dobro.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_items",
        verbose_name="aluno",
    )
    rule = models.CharField(
        max_length=200,
        verbose_name="regra",
        help_text="A regra de inglês que o aluno errou, como o avaliador a escreve, em inglês.",
    )
    box = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="caixa",
        help_text="Índice da caixa de intervalo: 0 é a de 1 dia, 6 é a de 120 dias.",
    )
    due_on = models.DateField(
        verbose_name="volta em",
        help_text="Dia em que o item fica vencido e entra na revisão.",
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="arquivado em",
        help_text=(
            "Quando o aluno marcou 'Não disse isso'. O item arquivado sai das rodadas e da "
            "contagem de vencidos, mas continua aqui para auditoria."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    class Meta:
        ordering = ["due_on", "id"]
        indexes = [models.Index(fields=["user", "due_on"], name="review_item_user_due")]
        verbose_name = "item de revisão"
        verbose_name_plural = "itens de revisão"

    def __str__(self) -> str:
        return f"{self.user} · {self.rule}"


class ReviewOccurrence(models.Model):
    """Uma vez em que o aluno errou na regra de um item, numa sessão.

    Guarda o que ele disse e a forma correta, e a tentativa de origem dá a cena e a data.
    É o histórico da auditoria: o item nunca perde de onde o erro veio. A explicação e os
    exemplos são do relatório da sessão, que pode mostrar a resposta; a rodada de revisão
    não os usa, porque ali o aluno precisa lembrar a forma correta sozinho.
    """

    item = models.ForeignKey(
        ReviewItem,
        on_delete=models.CASCADE,
        related_name="occurrences",
        verbose_name="item",
    )
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name="review_occurrences",
        verbose_name="tentativa",
    )
    produced = models.TextField(
        verbose_name="o aluno disse",
        help_text="A frase inteira que o aluno disse, com o erro dentro dela.",
    )
    correct = models.TextField(
        verbose_name="forma correta",
        help_text="A mesma frase corrigida, mantendo o que o aluno quis dizer.",
    )
    note = models.TextField(
        blank=True,
        default="",
        verbose_name="nota",
        help_text=(
            "Frase curta, em português, que diz o que observar na frase sem escrever o "
            "inglês correto. Vazia nos itens criados antes de a nota existir."
        ),
    )
    explanation = models.TextField(
        blank=True,
        default="",
        verbose_name="explicação",
        help_text=(
            "A regra explicada em português para o relatório da sessão. Diferente da nota, "
            "pode mostrar a forma correta. Vazia nas ocorrências anteriores à explicação."
        ),
    )
    examples = models.JSONField(
        blank=True,
        default=list,
        verbose_name="exemplos",
        help_text=(
            "Até duas frases curtas em inglês que aplicam a mesma regra em outras situações, "
            "mostradas no relatório da sessão."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="registrada em")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "ocorrência"
        verbose_name_plural = "ocorrências"

    def __str__(self) -> str:
        return f"{self.item.rule}: {self.produced}"
