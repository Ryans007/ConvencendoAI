from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.review.services.discard import ItemAlreadyArchived, discard_item
from apps.review.services.queries import active_items


class ReviewItemDiscardView(APIView):
    """Arquiva um item de revisão do aluno autenticado, a pedido dele ("Não disse isso").

    Um item de outro aluno, ou que já está arquivado, responde como inexistente: quem
    pergunta de fora não distingue "não é seu" de "não existe".
    """

    @extend_schema(
        summary="Arquivar um item de revisão",
        request=None,
        responses={204: None, 404: None},
    )
    def post(self, request: Request, item_id: int) -> Response:
        item = get_object_or_404(active_items(request.user), pk=item_id)
        try:
            discard_item(item)
        except ItemAlreadyArchived:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
