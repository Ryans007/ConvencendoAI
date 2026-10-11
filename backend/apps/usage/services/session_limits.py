from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.progress.models import Attempt
from apps.usage.models import AccessLimits, LiveSessionLease

LEASE_LIFETIME = timedelta(minutes=60)

SESSION_ALREADY_OPEN = "session_already_open"
DAILY_SESSION_LIMIT = "daily_session_limit"


class SessionRefused(Exception):
    """A sessão de voz não pode abrir: o aluno já está no limite. `code` é o contrato com a tela."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def open_session_lease(user) -> LiveSessionLease:
    """Reserva uma sessão de voz para o aluno, ou recusa por já estar no limite.

    A checagem e a criação rodam numa transação que trava a linha do aluno: sem a trava, duas
    abas abrindo no mesmo instante contariam as duas "nenhuma aberta" e passariam as duas. As
    concessões vencidas são apagadas aqui, então uma queda do servidor nunca prende o aluno
    por mais que o tempo máximo. O teto do dia conta as tentativas iniciadas desde a meia-noite
    do fuso do sistema, e a recusa por sessão aberta vem antes da do teto, porque é a que o
    aluno resolve na hora.
    """
    limits = AccessLimits.get_solo()
    now = timezone.now()
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        LiveSessionLease.objects.filter(user=user, expires_at__lte=now).delete()

        if LiveSessionLease.objects.filter(user=user).count() >= limits.max_open_voice_sessions:
            raise SessionRefused(SESSION_ALREADY_OPEN)

        today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        started_today = Attempt.objects.filter(user=user, started_at__gte=today).count()
        if started_today >= limits.max_voice_sessions_per_day:
            raise SessionRefused(DAILY_SESSION_LIMIT)

        return LiveSessionLease.objects.create(user=user, expires_at=now + LEASE_LIFETIME)


def release_session_lease(lease: LiveSessionLease | None) -> None:
    """Libera a sessão reservada quando a conexão termina, por qualquer motivo."""
    if lease is not None:
        LiveSessionLease.objects.filter(pk=lease.pk).delete()


def turn_audio_limit_bytes() -> int:
    """O tamanho máximo, em bytes, do áudio de um turno, lido da configuração."""
    return AccessLimits.get_solo().max_turn_audio_kb * 1024
