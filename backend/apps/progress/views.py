from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework.generics import RetrieveAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.progress.models import Attempt
from apps.progress.serializers import AttemptReportSerializer, TrackStateSerializer
from apps.progress.services.journey import build_journey

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
        "You did a good job explaining the problem and confirming the plan. Your "
        "sentences were clear enough for the receptionist to understand, but you could "
        "improve by making them more concise and reducing hesitation."
    ),
    "completed_at": "2026-09-06T20:57:11.810833-03:00",
    "score_breakdowns": [
        {"dimension": "objective", "value": 30, "weight": 30},
        {"dimension": "fluency", "value": 11, "weight": 15},
        {"dimension": "vocabulary", "value": 6, "weight": 10},
        {"dimension": "grammar", "value": 10, "weight": 15},
        {"dimension": "pragmatics", "value": 13, "weight": 15},
        {"dimension": "autonomy", "value": 4, "weight": 5},
    ],
    "criteria": [
        {"code": "c1", "text": "Explicou claramente qual é o problema do quarto", "met": True},
        {"code": "c2", "text": "Informou o número do quarto ou em que andar está", "met": True},
        {"code": "c3", "text": "Pediu uma solução concreta (trocar de quarto ou consertar hoje)", "met": True},
        {"code": "c4", "text": "Confirmou o que a recepção vai fazer e quando", "met": True},
    ],
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
    final, sub-nota de cada dimensão avaliada, resultado de cada critério aplicável ao
    nível, e o feedback do avaliador.

    Uma tentativa de outro aluno, ou uma tentativa própria ainda em andamento, devolve
    404 — o mesmo caso, para quem pergunta de fora, de "essa tentativa não existe". Não
    existe relatório parcial de uma sessão em andamento.
    """

    serializer_class = AttemptReportSerializer

    def get_queryset(self):
        return Attempt.objects.filter(user=self.request.user, completed_at__isnull=False)
