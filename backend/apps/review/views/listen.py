from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.review.models import ReviewAnswer
from apps.review.services.answering import AnswerFailed
from apps.review.services.listening import correct_form_audio
from apps.usage.services.review_limits import review_limit_reached, too_many_requests_response

_FAILURE_DETAIL = "O serviço de IA está indisponível no momento. Tente de novo em alguns minutos."


class AnyAcceptNegotiation(BaseContentNegotiation):
    """Ignora o `Accept` do cliente: o áudio é devolvido como WAV de qualquer jeito.

    O renderizador do projeto é só JSON, então a negociação padrão responderia 406 a quem
    pede `audio/wav`, que é exatamente o que um cliente de áudio faz.
    """

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class ReviewAnswerAudioView(APIView):
    """Devolve o áudio da forma correta revelada numa resposta do aluno autenticado.

    Uma resposta que não é do aluno, ou em que nada foi revelado, responde como inexistente:
    antes do fim da etapa a forma correta é a resposta, e o áudio não pode adiantá-la.
    """

    content_negotiation_class = AnyAcceptNegotiation

    @extend_schema(
        summary="Ouvir a forma correta de uma resposta da revisão",
        responses={(200, "audio/wav"): bytes, 404: None},
    )
    def get(self, request: Request, answer_id: int) -> Response:
        answers = ReviewAnswer.objects.filter(item__user=request.user).exclude(revealed_correct="")
        answer = get_object_or_404(answers, pk=answer_id)
        if review_limit_reached(request.user):
            return too_many_requests_response()
        try:
            audio = correct_form_audio(answer)
        except AnswerFailed as failure:
            return Response(
                {"code": failure.code.value, "detail": _FAILURE_DETAIL},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = HttpResponse(audio, content_type="audio/wav")
        response["Cache-Control"] = "private, max-age=3600"
        return response
