from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from apps.review.serializers import ReviewRoundItemSerializer
from apps.review.services.round import ROUND_SIZE, round_items


class ReviewRoundPagination(PageNumberPagination):
    """A rodada tem 5 itens por página: a primeira página é a rodada."""

    page_size = ROUND_SIZE


@extend_schema(
    summary="Rodada de revisão do aluno autenticado",
    examples=[
        OpenApiExample(
            "Rodada com dois itens",
            value={
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 12,
                        "said": "I have worked there yesterday",
                        "note": "Repare no tempo da frase: ele já terminou.",
                        "scenario_title": "Entrevista de emprego na TechCorp",
                        "occurred_at": "2026-10-04T14:32:10Z",
                        "interval_days": 3,
                        "mastered": False,
                        "step": 1,
                        "attempt": 1,
                        "correct": "",
                    },
                    {
                        "id": 15,
                        "said": "She explained me the process",
                        "note": "",
                        "scenario_title": "Entrevista de emprego na TechCorp",
                        "occurred_at": "2026-10-04T14:32:10Z",
                        "interval_days": 1,
                        "mastered": False,
                        "step": 2,
                        "attempt": 1,
                        "correct": "She explained the process to me.",
                    },
                ],
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class ReviewRoundView(ListAPIView):
    """Devolve os itens vencidos e não arquivados do aluno autenticado, na ordem da rodada.

    É uma listagem paginada de 5 em 5. "Mais uma rodada" pede a primeira página de novo: os
    itens que o aluno terminou ganharam um vencimento futuro e já saíram dela.
    """

    serializer_class = ReviewRoundItemSerializer
    pagination_class = ReviewRoundPagination

    def get_queryset(self):
        return round_items(self.request.user, timezone.localdate())
