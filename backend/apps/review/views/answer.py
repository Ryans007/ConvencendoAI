from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.review.serializers import (
    ReviewAnswerResponseSerializer,
    ReviewAnswerUploadSerializer,
    answer_payload,
)
from apps.review.services.answering import AnswerFailed, ProgressChanged, answer_item
from apps.review.services.queries import due_items

_FAILURE_DETAIL = "O serviço de IA está indisponível no momento. Tente de novo em alguns minutos."
_CHANGED_DETAIL = "Este item já foi respondido. Recarregue a rodada."


class ReviewAnswerView(APIView):
    """Recebe a resposta falada do aluno a um item da rodada, julga e devolve o veredito.

    O item precisa ser do aluno, estar vencido e não estar arquivado; senão, responde como
    inexistente. A etapa e a tentativa são decididas aqui, nunca pelo pedido. Uma falha do
    provedor responde 503 com um código estável e não grava nada, para o aluno reenviar o
    mesmo áudio, e um envio duplicado responde 409.
    """

    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Responder um item da revisão com a voz",
        request={"multipart/form-data": ReviewAnswerUploadSerializer},
        responses={200: ReviewAnswerResponseSerializer},
        examples=[
            OpenApiExample(
                "Primeiro erro da etapa 1",
                value={
                    "status": "judged",
                    "answer_id": 31,
                    "heard": "I have worked there yesterday",
                    "correct": False,
                    "feedback": "Repare em yesterday: ele marca um tempo que já terminou.",
                    "revealed_correct": "",
                    "next": {"step": 1, "attempt": 2},
                    "result": None,
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def post(self, request: Request, item_id: int) -> Response:
        today = timezone.localdate()
        item = get_object_or_404(due_items(request.user, today), pk=item_id)
        upload = ReviewAnswerUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)

        try:
            answered = answer_item(item, upload.validated_data["audio"].read(), today)
        except AnswerFailed as failure:
            return Response(
                {"code": failure.code.value, "detail": _FAILURE_DETAIL},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ProgressChanged:
            return Response({"detail": _CHANGED_DETAIL}, status=status.HTTP_409_CONFLICT)
        return Response(ReviewAnswerResponseSerializer(answer_payload(answered)).data)
