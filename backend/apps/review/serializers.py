from rest_framework import serializers


class ReviewSummarySerializer(serializers.Serializer):
    """Resumo da revisão do aluno, para o selo do menu e a barra da jornada."""

    due = serializers.IntegerField(help_text="Quantos itens de revisão estão vencidos hoje.")
    next_due_on = serializers.DateField(
        allow_null=True,
        help_text="Dia do próximo vencimento entre os itens que ainda não venceram, ou nulo.",
    )
