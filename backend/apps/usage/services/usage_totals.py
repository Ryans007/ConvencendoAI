from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Q, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.usage.models import ModelUsage


@dataclass(frozen=True)
class UsageRow:
    """O consumo somado de um recorte: por papel e modelo, ou o total de um filtro."""

    purpose: str
    model_id: str
    calls: int
    failures: int
    input_tokens: int
    output_tokens: int
    billed_audio_seconds: float
    characters: int
    cost_usd: Decimal
    unpriced_calls: int


def month_start(now: datetime | None = None) -> datetime:
    """O primeiro instante do mês corrente, no fuso do sistema."""
    local = timezone.localtime(now or timezone.now())
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _sums() -> dict:
    return {
        "calls": Count("id"),
        "failures": Count("id", filter=Q(failed=True)),
        "input_tokens": Sum("input_tokens"),
        "output_tokens": Sum("output_tokens"),
        "billed_audio_seconds": Sum("billed_audio_seconds"),
        "characters": Sum("characters"),
        "cost_usd": Sum("cost_usd"),
        "unpriced_calls": Count("id", filter=Q(priced=False, failed=False)),
    }


def _row(values: dict, purpose: str = "", model_id: str = "") -> UsageRow:
    return UsageRow(
        purpose=purpose,
        model_id=model_id,
        calls=values["calls"] or 0,
        failures=values["failures"] or 0,
        input_tokens=values["input_tokens"] or 0,
        output_tokens=values["output_tokens"] or 0,
        billed_audio_seconds=values["billed_audio_seconds"] or 0.0,
        characters=values["characters"] or 0,
        cost_usd=values["cost_usd"] or Decimal(0),
        unpriced_calls=values["unpriced_calls"] or 0,
    )


def usage_totals(usages: QuerySet[ModelUsage]) -> UsageRow:
    """Soma de um conjunto de linhas de uso, como o recorte filtrado da tela de uso."""
    return _row(usages.order_by().aggregate(**_sums()))


def usage_breakdown(user, since: datetime | None = None) -> list[UsageRow]:
    """O uso de um aluno separado por papel e por modelo, do início ou desde `since`."""
    usages = ModelUsage.objects.filter(user=user)
    if since is not None:
        usages = usages.filter(created_at__gte=since)
    rows = (
        usages.order_by()
        .values("purpose", "model_id_at_time")
        .annotate(**_sums())
        .order_by("purpose", "model_id_at_time")
    )
    return [_row(row, row["purpose"], row["model_id_at_time"]) for row in rows]


def month_usage_annotations(since: datetime) -> dict:
    """Anotações dos tokens e do custo do mês de cada usuário, sem multiplicar as junções.

    Cada soma é uma subconsulta própria, porque a lista de usuários já junta as tentativas, e
    juntar também o uso multiplicaria as linhas e inflaria as somas.
    """
    month = ModelUsage.objects.filter(user=OuterRef("pk"), created_at__gte=since).order_by().values(
        "user"
    )
    tokens = month.annotate(total=Sum(F("input_tokens") + F("output_tokens"))).values("total")
    cost = month.annotate(total=Sum("cost_usd")).values("total")
    return {
        "month_tokens": Coalesce(Subquery(tokens), Value(0)),
        "month_cost": Coalesce(
            Subquery(cost),
            Value(Decimal(0)),
            output_field=DecimalField(max_digits=14, decimal_places=8),
        ),
    }
