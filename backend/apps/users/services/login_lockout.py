from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.usage.models import AccessLimits
from apps.users.models import LoginFailure


def _remaining(
    failures: QuerySet[LoginFailure],
    max_failures: int,
    window: timedelta,
    lockout: timedelta,
    now: datetime,
) -> timedelta:
    """Quanto falta de bloqueio para um conjunto de falhas: o de um usuário ou o de um IP.

    O bloqueio começa quando a última falha fecha, numa janela que termina nela, o número
    máximo de falhas, e dura o tempo de bloqueio a partir dessa falha. Como as tentativas
    recusadas pelo bloqueio não viram falha, a última falha gravada é a que o iniciou, e o
    bloqueio não se renova sozinho. Uma rajada antiga não bloqueia ninguém: o fim do bloqueio
    dela já passou.
    """
    latest = failures.order_by("-created_at").values_list("created_at", flat=True).first()
    if latest is None:
        return timedelta(0)
    until = latest + lockout
    if until <= now:
        return timedelta(0)
    in_window = failures.filter(created_at__gt=latest - window, created_at__lte=latest).count()
    return until - now if in_window >= max_failures else timedelta(0)


def login_lock_remaining_seconds(
    username: str, ip_address: str | None, now: datetime | None = None
) -> int:
    """Quantos segundos faltam para o usuário e o IP poderem tentar de novo; 0 se não há bloqueio.

    Vale o maior dos dois: o usuário bloqueado por senhas erradas para ele, ou o IP bloqueado
    por senhas erradas vindas dele, para qualquer usuário. Os limites e os tempos vêm da
    configuração, lida a cada chamada.
    """
    now = now or timezone.now()
    limits = AccessLimits.get_solo()
    window = timedelta(minutes=limits.login_window_minutes)
    lockout = timedelta(minutes=limits.login_lockout_minutes)

    remaining = _remaining(
        LoginFailure.objects.filter(username=username),
        limits.login_max_failures_per_user,
        window,
        lockout,
        now,
    )
    if ip_address:
        remaining = max(
            remaining,
            _remaining(
                LoginFailure.objects.filter(ip_address=ip_address),
                limits.login_max_failures_per_ip,
                window,
                lockout,
                now,
            ),
        )
    return int(remaining.total_seconds()) + (1 if remaining.total_seconds() % 1 else 0)


def clear_login_failures(username: str) -> None:
    """Zera as senhas erradas de um usuário depois de um login certo."""
    LoginFailure.objects.filter(username=username).delete()
