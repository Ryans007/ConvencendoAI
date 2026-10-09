from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.review.serializers import ReviewSummarySerializer
from apps.review.services.summary import review_summary


class ReviewSummaryView(APIView):
    """Devolve quantos itens de revisão do aluno autenticado estão vencidos.

    Não é uma listagem, e sim um agregado de dois números, então não tem paginação. A data
    de hoje é a do fuso do sistema, para "vence hoje" significar o dia do aluno.
    """

    @extend_schema(
        summary="Resumo da revisão do aluno autenticado",
        responses=ReviewSummarySerializer,
        examples=[
            OpenApiExample(
                "Itens vencidos",
                value={"due": 3, "next_due_on": "2026-10-09"},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Sem itens",
                value={"due": 0, "next_due_on": None},
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        summary = review_summary(request.user, timezone.localdate())
        return Response(ReviewSummarySerializer(summary).data)
