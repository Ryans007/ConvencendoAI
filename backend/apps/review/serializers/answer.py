from rest_framework import serializers

from apps.review.services.answering import AnsweredItem, AnswerStatus
from apps.review.services.schedule import BOX_INTERVAL_DAYS, LAST_BOX

MAX_AUDIO_BYTES = 2 * 1024 * 1024
ACCEPTED_AUDIO_TYPES = frozenset({"audio/webm", "audio/ogg", "audio/mp4", "audio/wav"})


class ReviewAnswerUploadSerializer(serializers.Serializer):
    """O áudio de uma resposta falada, validado antes de gastar uma transcrição.

    O limite de 2 MB cobre minutos de fala, muito mais do que uma frase, e existe para o
    envio não virar uma forma de gastar o provedor de STT. O tipo vem do próprio arquivo
    enviado, sem parâmetros como `codecs`.
    """

    audio = serializers.FileField(help_text="Gravação da fala do aluno, até 2 MB.")

    def validate_audio(self, audio):
        if audio.size == 0:
            raise serializers.ValidationError("O áudio está vazio.")
        if audio.size > MAX_AUDIO_BYTES:
            raise serializers.ValidationError("O áudio é grande demais.")
        if audio.content_type not in ACCEPTED_AUDIO_TYPES:
            raise serializers.ValidationError("Esse tipo de áudio não é aceito.")
        return audio


class NextStepSerializer(serializers.Serializer):
    """A etapa e a tentativa da próxima resposta de um item."""

    step = serializers.IntegerField(help_text="1 (frase corrigida) ou 2 (frase nova).")
    attempt = serializers.IntegerField(help_text="1 ou 2.")


class ItemResultSerializer(serializers.Serializer):
    """O que a revisão terminada fez com o item no calendário."""

    outcome = serializers.CharField(help_text="first_try, second_try ou failed.")
    interval_days = serializers.IntegerField(help_text="Intervalo, em dias, da nova caixa.")
    due_on = serializers.DateField(help_text="Novo vencimento do item.")
    mastered = serializers.BooleanField(help_text="O item ficou dominado.")


class ReviewAnswerResponseSerializer(serializers.Serializer):
    """O veredito de uma resposta e para onde o item vai.

    `revealed_correct` só vem preenchida quando a etapa terminou, e `next` e `result` são
    exclusivos: enquanto o item tem etapa a cumprir vem `next`, e quando a revisão termina
    vem `result`. Quando nada foi ouvido, só `status` tem valor.
    """

    status = serializers.ChoiceField(choices=[status.value for status in AnswerStatus])
    answer_id = serializers.IntegerField(allow_null=True)
    heard = serializers.CharField(allow_blank=True, help_text="O que ouvimos na fala do aluno.")
    correct = serializers.BooleanField(allow_null=True, help_text="Se o professor aprovou.")
    feedback = serializers.CharField(allow_blank=True, help_text="Feedback em português.")
    revealed_correct = serializers.CharField(
        allow_blank=True, help_text="Forma correta, só quando a etapa terminou."
    )
    next = NextStepSerializer(allow_null=True)
    result = ItemResultSerializer(allow_null=True)


def answer_payload(answered: AnsweredItem) -> dict:
    """Monta, a partir do que o serviço produziu, o que a resposta da API carrega."""
    if answered.answer is None:
        return {
            "status": answered.status.value,
            "answer_id": None,
            "heard": "",
            "correct": None,
            "feedback": "",
            "revealed_correct": "",
            "next": None,
            "result": None,
        }
    answer, result, upcoming = answered.answer, answered.result, answered.next_progress
    return {
        "status": answered.status.value,
        "answer_id": answer.pk,
        "heard": answer.heard,
        "correct": answer.correct,
        "feedback": answer.feedback,
        "revealed_correct": answer.revealed_correct,
        "next": {"step": upcoming.step, "attempt": upcoming.attempt} if upcoming else None,
        "result": (
            {
                "outcome": result.outcome,
                "interval_days": BOX_INTERVAL_DAYS[min(result.box_after, LAST_BOX)],
                "due_on": result.due_on_after,
                "mastered": answered.mastered,
            }
            if result
            else None
        ),
    }
