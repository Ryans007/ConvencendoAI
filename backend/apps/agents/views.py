from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.serializers import ScenarioBriefingSerializer
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario
from apps.progress.services.memory import track_memory

_BRIEFING_EXAMPLE = {
    "title": "Negociar prazo com a PM",
    "objective": (
        "Conseguir uma semana extra de prazo para entregar o módulo em que você está "
        "trabalhando."
    ),
    "context": (
        "Você já trabalha na TechCorp. O escopo do módulo aumentou depois do combinado e "
        "a entrega original não é viável. Rachel agora é a PM do produto e Tom é seu "
        "tech lead."
    ),
    "difficulty_label": "Conversa livre",
    "expected_cefr": "A2-B1",
    "max_turns": 12,
    "roles": [
        {"name": "Rachel", "scene_function": "PM do produto", "archetype": "Gatekeeper"},
        {"name": "Tom", "scene_function": "tech lead, seu colega", "archetype": "Aliado"},
    ],
    "memory_summary": (
        "Backend developer role; built payment processing service; asked about team "
        "structure and hiring steps; minimal grammar issues, could improve lexical "
        "variety."
    ),
}


class ScenarioBriefingView(APIView):
    """Devolve o briefing pré-sessão de um cenário e nível: objetivo, contexto, elenco,
    limite de turnos e o resumo de memória da trilha, se houver — o que o aluno deveria
    ver antes de iniciar a execução, seja por texto (management command) ou por voz
    (WebSocket).

    Nunca inclui os critérios de aceite nem os pesos da rubrica de avaliação — esses só
    aparecem no relatório, depois da sessão, para não permitir que o aluno "decore a
    prova" antes de conversar.
    """

    @extend_schema(
        summary="Briefing pré-sessão de um cenário e nível",
        parameters=[
            OpenApiParameter(
                "scenario_slug", str, OpenApiParameter.PATH, description="Slug do cenário."
            ),
            OpenApiParameter(
                "level_order", int, OpenApiParameter.PATH, description="Ordem do nível (1 a 3)."
            ),
        ],
        responses={
            200: ScenarioBriefingSerializer,
            404: OpenApiResponse(description="Cenário ou nível inexistente."),
        },
        examples=[
            OpenApiExample(
                "Briefing com memória de um cenário anterior na trilha",
                value=_BRIEFING_EXAMPLE,
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request: Request, scenario_slug: str, level_order: int) -> Response:
        scenario = get_object_or_404(Scenario, slug=scenario_slug)
        level = get_object_or_404(Level, order=level_order)
        content = load_scenario_content(scenario, level)
        memory = track_memory(request.user, scenario)

        payload = {
            "title": content.title,
            "objective": content.objective,
            "context": content.context,
            "difficulty_label": content.difficulty_label,
            "expected_cefr": content.expected_cefr,
            "max_turns": content.max_turns,
            "roles": [
                {"name": role.name, "scene_function": role.scene_function, "archetype": role.archetype}
                for role in content.roles
            ],
            "memory_summary": memory,
        }
        serializer = ScenarioBriefingSerializer(payload)
        return Response(serializer.data)
