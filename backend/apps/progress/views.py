from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.progress.models import Attempt
from apps.progress.serializers import AttemptReportSerializer, TrackStateSerializer
from apps.progress.services.attempt_report import build_attempt_report
from apps.progress.services.journey import build_journey
from apps.review.models import ReviewOccurrence
from apps.review.services.answering import AnswerFailed
from apps.review.services.listening import occurrence_correct_audio
from apps.review.views.listen import AnyAcceptNegotiation
from apps.usage.services.review_limits import review_limit_reached, too_many_requests_response

_AUDIO_FAILURE_DETAIL = (
    "O serviço de IA está indisponível no momento. Tente de novo em alguns minutos."
)

_JOURNEY_EXAMPLE = [
    {
        "slug": "carreira-em-ti",
        "title": "Carreira em TI",
        "order": 1,
        "student_role": "Você é um(a) desenvolvedor(a) backend.",
        "unlocked": True,
        "completed": True,
        "approved_levels": 2,
        "possible_levels": 6,
        "performance": 92.0,
        "scenario_states": [
            {
                "slug": "entrevista-de-emprego",
                "title": "Entrevista de emprego na TechCorp",
                "order": 1,
                "completed": True,
                "unlocked": True,
                "cast": [
                    {"name": "Rachel", "scene_function": "recrutadora de RH"},
                    {"name": "Tom", "scene_function": "tech lead do time de backend"},
                ],
                "level_states": [
                    {
                        "order": 1,
                        "name": "Ouvir",
                        "expected_cefr": "A1-A2",
                        "expected_production": (
                            "Compreensão auditiva: responde perguntas fechadas com sim, "
                            "não ou uma escolha simples."
                        ),
                        "approved": False,
                        "available": True,
                        "cooldown_remaining_seconds": None,
                        "last_attempt": None,
                    },
                    {
                        "order": 3,
                        "name": "Conversa livre",
                        "expected_cefr": "A2-B1",
                        "expected_production": (
                            "Produção livre: conversa consolidada, sem restrição de "
                            "formato de resposta."
                        ),
                        "approved": True,
                        "available": True,
                        "cooldown_remaining_seconds": None,
                        "last_attempt": {
                            "id": 42,
                            "final_score": 90,
                            "passed": True,
                            "completed_at": "2026-09-29T14:32:10Z",
                        },
                    },
                ],
            }
        ],
    }
]

_ATTEMPT_REPORT_EXAMPLE = {
    "id": 22,
    "scenario": "problema-no-quarto",
    "level": 3,
    "final_score": 82,
    "passed": True,
    "feedback": (
        "Você explicou bem o problema do quarto e confirmou o que a recepção ia fazer. "
        "O ponto mais importante a melhorar é começar a responder mais rápido: numa "
        "conversa real, pausas longas antes de falar passam insegurança."
    ),
    "completed_at": "2026-09-06T20:57:11.810833-03:00",
    "hints_enabled": False,
    "hints_used": 0,
    "score_breakdowns": [
        {"dimension": "objective", "value": 30, "weight": 30, "comment": ""},
        {
            "dimension": "fluency",
            "value": 11,
            "weight": 15,
            "comment": "Você levou cerca de 4 segundos para começar a responder.",
        },
        {"dimension": "vocabulary", "value": 6, "weight": 10, "comment": ""},
        {"dimension": "grammar", "value": 10, "weight": 15, "comment": ""},
        {"dimension": "pragmatics", "value": 13, "weight": 15, "comment": ""},
        {"dimension": "autonomy", "value": 4, "weight": 5, "comment": ""},
    ],
    "criteria": [
        {"code": "c1", "text": "Explicou claramente qual é o problema do quarto", "met": True},
        {"code": "c2", "text": "Informou o número do quarto ou em que andar está", "met": True},
        {"code": "c3", "text": "Pediu uma solução concreta (trocar de quarto ou consertar hoje)", "met": True},
        {"code": "c4", "text": "Confirmou o que a recepção vai fazer e quando", "met": True},
    ],
    "mistakes": [
        {
            "id": 7,
            "produced": "I want to report today, please.",
            "correct": "I want to repair it today, please.",
            "explanation": "Aqui o verbo é o de consertar (repair), e não o de relatar (report).",
            "examples": ["Can you repair the shower?", "They repaired the AC yesterday."],
        }
    ],
    "speech_metrics": {
        "reaction_seconds": 4.0,
        "words_per_minute": 92.0,
        "long_pauses_per_100_words": 3.1,
        "lexical_diversity": 0.62,
        "lexical_range": 0.06,
    },
    "scoring": {
        "passing_score": 70,
        "fluency": {
            "measured_share": 0.7,
            "reaction_share": 0.4,
            "speed_share": 0.4,
            "pauses_share": 0.2,
        },
        "vocabulary": {"judged_share": 0.5, "diversity_share": 0.25, "range_share": 0.25},
    },
}


class JourneyView(APIView):
    """Devolve a jornada inteira do aluno autenticado: todas as trilhas, seus cenários e
    níveis, com o estado de progresso de cada um calculado a partir das tentativas reais
    do aluno (liberado, concluído, aprovado, em cooldown).

    Devolvida inteira, numa única resposta, sem paginação — não é uma listagem de banco
    que cresce com o uso, é um agregado calculado sobre um número de trilhas que cresce
    devagar, por conteúdo cadastrado, não por atividade do aluno.
    """

    @extend_schema(
        summary="Jornada do aluno autenticado",
        responses=TrackStateSerializer(many=True),
        examples=[
            OpenApiExample(
                "Jornada com uma trilha concluída",
                value=_JOURNEY_EXAMPLE,
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        journey = build_journey(request.user)
        serializer = TrackStateSerializer(journey, many=True)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        summary="Relatório de uma tentativa concluída",
        examples=[
            OpenApiExample(
                "Tentativa aprovada",
                value=_ATTEMPT_REPORT_EXAMPLE,
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
)
class AttemptReportView(RetrieveAPIView):
    """Devolve o relatório de uma tentativa do aluno autenticado, já concluída: nota
    final, sub-nota e comentário de cada dimensão avaliada, resultado de cada critério
    aplicável ao nível, resumo do avaliador, erros da sessão, medidas de fala e a conta.

    Uma tentativa de outro aluno, ou uma tentativa própria ainda em andamento, devolve
    404 — o mesmo caso, para quem pergunta de fora, de "essa tentativa não existe". Não
    existe relatório parcial de uma sessão em andamento.
    """

    serializer_class = AttemptReportSerializer

    def get_queryset(self):
        return Attempt.objects.filter(user=self.request.user, completed_at__isnull=False)

    def get_object(self):
        return build_attempt_report(super().get_object())


class AttemptMistakeAudioView(APIView):
    """Devolve o áudio da forma correta de um erro do relatório de uma tentativa.

    Um erro de tentativa de outro aluno, ou de tentativa em andamento, responde como
    inexistente, como o próprio relatório. O uso entra no limite por minuto do "Ouvir" da
    revisão, porque é a mesma síntese.
    """

    content_negotiation_class = AnyAcceptNegotiation

    @extend_schema(
        summary="Ouvir a forma correta de um erro do relatório",
        responses={(200, "audio/wav"): bytes, 404: None, 429: None, 503: None},
    )
    def get(self, request: Request, pk: int, occurrence_id: int) -> Response:
        occurrences = ReviewOccurrence.objects.select_related("item", "attempt").filter(
            attempt_id=pk, attempt__user=request.user, attempt__completed_at__isnull=False
        )
        occurrence = get_object_or_404(occurrences, pk=occurrence_id)
        if review_limit_reached(request.user):
            return too_many_requests_response()
        try:
            audio = occurrence_correct_audio(occurrence)
        except AnswerFailed as failure:
            return Response(
                {"code": failure.code.value, "detail": _AUDIO_FAILURE_DETAIL},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = HttpResponse(audio, content_type="audio/wav")
        response["Cache-Control"] = "private, max-age=3600"
        return response
