"""Endpoints de infraestrutura, sem dominio de produto."""

from typing import Any

from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Reporta se a aplicacao responde e se o banco esta alcancavel."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """Devolve o estado da aplicacao e do banco.

        Responde 503 quando o banco nao responde, para que um verificador externo
        distinga "a aplicacao subiu" de "a aplicacao subiu e alcanca suas dependencias".
        """
        database_reachable = self._database_reachable()
        payload: dict[str, Any] = {
            "application": "ok",
            "database": "ok" if database_reachable else "unreachable",
        }
        http_status = (
            status.HTTP_200_OK if database_reachable else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(payload, status=http_status)

    @staticmethod
    def _database_reachable() -> bool:
        """Executa uma consulta trivial e informa se o banco respondeu."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
        except DatabaseError:
            return False
