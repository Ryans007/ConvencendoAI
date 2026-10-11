from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.usage.models import AccessLimits, ModelUsage

TOO_MANY_REQUESTS_CODE = "too_many_requests"
_WINDOW = timedelta(minutes=1)


def review_limit_reached(user) -> bool:
    """O aluno já fez, no último minuto, o máximo de chamadas a modelos pela revisão.

    Conta as linhas de uso de modelo ligadas a um item de revisão do aluno, que é o que de fato
    custa: a transcrição, o julgamento e a síntese. Chamadas que falharam também contam, porque
    o provedor foi chamado. O limite vem da configuração, lida a cada chamada.
    """
    since = timezone.now() - _WINDOW
    calls = ModelUsage.objects.filter(
        user=user, review_item__isnull=False, created_at__gte=since
    ).count()
    return calls >= AccessLimits.get_solo().max_review_calls_per_minute


def too_many_requests_response() -> Response:
    """A resposta 429 da revisão: o código que a tela trata sem gastar a tentativa do aluno."""
    return Response(
        {
            "code": TOO_MANY_REQUESTS_CODE,
            "detail": "Muitas respostas em pouco tempo. Tente de novo em um minuto.",
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": "60"},
    )
