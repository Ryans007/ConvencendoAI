import json
import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone

from apps.agents.evaluation import calibration, scorecard
from apps.agents.evaluation.case_loader import LoadedCases, load_cases
from apps.agents.evaluation.report import build_report
from apps.agents.evaluation.router_layer import run_router_layer, summarize_router
from apps.agents.evaluation.session_layer import run_session_layer
from apps.agents.evaluation.situation_layer import run_situation_layer
from apps.agents.services.round_trace import collect_round_events
from apps.llm.models import AgentModelConfig, LLMModel
from apps.llm.services.model_override import override_models
from apps.usage.models import ModelUsage
from apps.usage.services.owner import usage_owner

ALL_LAYERS = ("router", "situations", "sessions")
USAGE_LABEL = "avaliação"
DEFAULT_MAX_CALLS = 800
DEFAULT_OUTPUT_DIR = Path(".evaluation")

_PERSONA_CALLS_PER_ROUND = 3
_JUDGE_LINES_PER_ROUND = 2


class BudgetExceeded(Exception):
    """A execução escolhida faria mais chamadas a modelo que o teto informado."""


@dataclass
class EvaluationOptions:
    """O que uma execução da avaliação deve rodar e com quais limites."""

    layers: tuple[str, ...] = ALL_LAYERS
    scenario: str = ""
    level: int | None = None
    samples: int | None = None
    repetitions: int = 2
    use_judge: bool = True
    models: dict[str, LLMModel] = field(default_factory=dict)
    max_calls: int = DEFAULT_MAX_CALLS
    label: str = "run"
    calibration_sample: int = 0
    output_dir: Path = DEFAULT_OUTPUT_DIR
    seed: int | None = None


def select_cases(cases: LoadedCases, options: EvaluationOptions) -> LoadedCases:
    """Filtra os casos pelo cenário e pelo nível pedidos, mantendo o conteúdo já carregado."""

    def keep(scenario: str, level: int) -> bool:
        return (not options.scenario or scenario == options.scenario) and (
            options.level is None or level == options.level
        )

    return LoadedCases(
        router=[c for c in cases.router if keep(c.scenario, c.level)],
        situations=[s for s in cases.situations if keep(s.scenario, s.level)],
        students=[p for p in cases.students if keep(p.scenario, p.level)],
        targets=cases.targets,
        contents=cases.contents,
    )


def estimate_calls(cases: LoadedCases, options: EvaluationOptions) -> dict[str, int]:
    """O máximo de chamadas a modelo que cada camada faria, para recusar antes de gastar.

    São limites superiores, contando as chamadas extras de uma rodada com passagem de vez e do
    fechamento; o consumo real costuma ficar abaixo. O juiz entra quando está ligado.
    """
    estimate = {layer: 0 for layer in ALL_LAYERS}
    if "router" in options.layers:
        estimate["router"] = len(cases.router) * options.repetitions
    if "situations" in options.layers:
        for situation in cases.situations:
            semantic = sum(1 for e in situation.expectations if e.check == "judge")
            per_sample = _PERSONA_CALLS_PER_ROUND
            if options.use_judge:
                per_sample += _JUDGE_LINES_PER_ROUND + semantic
            estimate["situations"] += (options.samples or situation.samples) * per_sample
    if "sessions" in options.layers:
        for profile in cases.students:
            rounds = cases.contents[(profile.scenario, profile.level)].max_turns
            per_round = 2 + _PERSONA_CALLS_PER_ROUND
            if options.use_judge:
                per_round += _JUDGE_LINES_PER_ROUND
            estimate["sessions"] += rounds * per_round + 1
    return estimate


def _model_name(model: LLMModel | None) -> str:
    return f"{model.provider.code}/{model.model_id}" if model else "não configurado"


def _models_in_use(options: EvaluationOptions) -> dict[str, str]:
    config = AgentModelConfig.get_solo()
    chosen = {
        "persona": options.models.get("persona") or config.persona_model,
        "router": options.models.get("router") or config.router_model,
        "judge": options.models.get("judge") or config.judge_model,
    }
    return {purpose: _model_name(model) for purpose, model in chosen.items()}


def _usage_summary(started_at: datetime) -> dict[str, Any]:
    rows = ModelUsage.objects.filter(
        user__isnull=True, username_at_time=USAGE_LABEL, created_at__gte=started_at
    )
    by_purpose = [
        {
            "purpose": row["purpose"],
            "model": row["model_id_at_time"],
            "calls": row["calls"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
        }
        for row in rows.values("purpose", "model_id_at_time")
        .annotate(
            calls=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
        )
        .order_by("purpose", "model_id_at_time")
    ]
    durations = sorted(rows.filter(purpose="persona").values_list("duration_ms", flat=True))
    latency = None
    if durations:
        latency = {
            "median_s": statistics.median(durations) / 1000,
            "p90_s": durations[min(len(durations) - 1, int(len(durations) * 0.9))] / 1000,
            "count": len(durations),
        }
    priced = rows.filter(priced=True)
    return {
        "by_purpose": by_purpose,
        "persona_latency": latency,
        "cost_usd": float(priced.aggregate(total=Sum("cost_usd"))["total"] or 0),
        "unpriced": rows.filter(priced=False).count(),
    }


def run_evaluation(
    options: EvaluationOptions,
    *,
    progress: Callable[[str], None] = lambda message: None,
) -> tuple[Path | None, dict[str, int]]:
    """Valida os casos, confere o teto, roda as camadas e grava o relatório e os dados brutos.

    A ordem protege o custo: primeiro os casos são carregados e validados, depois a estimativa
    é conferida contra o teto, e só então a primeira chamada a modelo é feita. A execução inteira
    roda marcada como uso da avaliação e com os modelos escolhidos valendo só dentro dela.
    Devolve a pasta da execução e a estimativa de chamadas.
    """
    cases = select_cases(load_cases(), options)
    estimate = estimate_calls(cases, options)
    total = sum(estimate.values())
    if total > options.max_calls:
        raise BudgetExceeded(
            f"A execução faria até {total} chamadas a modelo e o teto é {options.max_calls}. "
            "Reduza as camadas, o cenário ou as amostras, ou aumente o teto."
        )

    started_at = timezone.now()
    router: list[dict[str, Any]] = []
    situations: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    with usage_owner(label=USAGE_LABEL), override_models(options.models), collect_round_events():
        if "router" in options.layers:
            router = run_router_layer(cases.router, cases.contents, options.repetitions, progress)
        if "situations" in options.layers:
            situations = run_situation_layer(
                cases.situations,
                cases.contents,
                samples=options.samples,
                use_judge=options.use_judge,
                progress=progress,
            )
        if "sessions" in options.layers:
            sessions = run_session_layer(
                cases.students, cases.contents, use_judge=options.use_judge, progress=progress
            )

    values = scorecard.metric_values(router, situations, sessions)
    run = {
        "label": options.label,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": timezone.now().isoformat(timespec="seconds"),
        "layers": [layer for layer in ALL_LAYERS if layer in options.layers],
        "calls_estimated": total,
        "models": _models_in_use(options),
        "overridden": sorted(options.models),
        "use_judge": options.use_judge,
        "scorecard": scorecard.evaluate_targets(values, cases.targets),
        "router": router,
        "router_summary": {
            key: value
            for key, value in summarize_router(router).items()
            if key not in ("errors", "ambiguous")
        },
        "situations": situations,
        "sessions": sessions,
        "role_items": scorecard.role_item_counts(situations, sessions),
        "usage": _usage_summary(started_at),
    }

    folder = options.output_dir / f"{started_at.strftime('%Y%m%d-%H%M%S')}-{options.label}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (folder / "report.md").write_text(build_report(run), encoding="utf-8")
    if options.calibration_sample and options.use_judge:
        calibration.write_review_file(
            calibration.judged_items(situations, sessions),
            options.calibration_sample,
            folder / "review.csv",
            random.Random(options.seed),
        )
    return folder, estimate
