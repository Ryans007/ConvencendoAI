from rest_framework import serializers

from apps.review.models import ReviewItem
from apps.review.services.item_progress import STEP_NEW_SENTENCE, item_progress
from apps.review.services.schedule import BOX_INTERVAL_DAYS, LAST_BOX, is_mastered


class ReviewRoundItemSerializer(serializers.Serializer):
    """Um item da rodada, como a tela do item o mostra.

    A forma correta só sai quando o item já está na etapa 2, porque antes disso ela é a
    própria resposta da etapa 1.
    """

    id = serializers.IntegerField(help_text="Identificador do item.")
    said = serializers.CharField(
        source="latest_produced", help_text="O que o aluno disse na ocorrência mais recente."
    )
    scenario_title = serializers.CharField(
        source="latest_scenario_title", help_text="Cenário em que o aluno cometeu o erro."
    )
    occurred_at = serializers.DateTimeField(
        source="latest_at", help_text="Quando o aluno cometeu o erro."
    )
    interval_days = serializers.SerializerMethodField(
        help_text="Intervalo, em dias, da caixa atual do item."
    )
    mastered = serializers.SerializerMethodField(help_text="O item está dominado.")
    step = serializers.SerializerMethodField(
        help_text="Etapa da próxima resposta: 1 (frase corrigida) ou 2 (frase nova)."
    )
    attempt = serializers.SerializerMethodField(help_text="Tentativa da próxima resposta: 1 ou 2.")
    correct = serializers.SerializerMethodField(
        help_text="Forma correta, só quando o item já está na etapa 2; antes disso é vazia."
    )

    def get_interval_days(self, item: ReviewItem) -> int:
        return BOX_INTERVAL_DAYS[min(item.box, LAST_BOX)]

    def get_mastered(self, item: ReviewItem) -> bool:
        return is_mastered(item.box)

    def get_step(self, item: ReviewItem) -> int:
        return item_progress(item.open_answers).step

    def get_attempt(self, item: ReviewItem) -> int:
        return item_progress(item.open_answers).attempt

    def get_correct(self, item: ReviewItem) -> str:
        if item_progress(item.open_answers).step == STEP_NEW_SENTENCE:
            return item.latest_correct
        return ""
