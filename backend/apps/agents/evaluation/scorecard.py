from collections import Counter
from typing import Any

from apps.agents.evaluation.case_loader import Target
from apps.agents.evaluation.router_layer import summarize_router
from apps.agents.evaluation.schemas import ROLE_ITEMS

SITUATION_RATE_CHECKS = (
    "passes_to",
    "no_handoff",
    "introduces",
    "single_question",
    "last_line_to_student",
    "speaker",
)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def situation_check_counts(situations: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """Por verificação estrutural, em quantas amostras ela se cumpriu e quantas a testaram."""
    done: Counter = Counter()
    total: Counter = Counter()
    for sample in situations:
        for item in sample.get("expectations", []):
            if item["check"] == "judge" or item["ok"] is None:
                continue
            total[item["check"]] += 1
            done[item["check"]] += 1 if item["ok"] else 0
    return {check: (done[check], total[check]) for check in total}


def role_item_counts(
    situations: list[dict[str, Any]], sessions: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """Por item da lista de verificação, quantas falas deram sim, não e não se aplica."""
    counts: dict[str, Counter] = {item: Counter() for item in ROLE_ITEMS}
    for source in (*situations, *sessions):
        for judged in source.get("roles", []):
            for item, verdict in judged.get("items", {}).items():
                counts[item][verdict["answer"]] += 1
    return {item: dict(counter) for item, counter in counts.items()}


def metric_values(
    router: list[dict[str, Any]],
    situations: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> dict[str, float | None]:
    """Calcula o valor de cada métrica das metas a partir dos resultados das três camadas."""
    values: dict[str, float | None] = {}
    summary = summarize_router(router)
    values["router_named_accuracy"] = _ratio(summary["named_correct"], summary["named_total"])
    values["router_false_call_rate"] = _ratio(summary["answer_wrong"], summary["answer_total"])
    values["router_topic_accuracy"] = _ratio(summary["topic_correct"], summary["topic_total"])

    counts = situation_check_counts(situations)
    for check in SITUATION_RATE_CHECKS:
        done, total = counts.get(check, (0, 0))
        values[f"{check}_rate"] = _ratio(done, total)

    measured = [s["metrics"] for s in sessions if "metrics" in s]
    if measured:
        rounds = sum(m["rounds"] for m in measured)
        values["session_dangling_rounds"] = sum(len(m["dangling_rounds"]) for m in measured)
        values["session_multi_question_rate"] = _ratio(
            sum(m["multi_question_rounds"] for m in measured), rounds
        )
        values["session_over_limit_runs"] = sum(m["over_limit_runs"] for m in measured)
        values["session_repeated_handoffs"] = sum(len(m["repeated_handoffs"]) for m in measured)
        values["session_intro_rate"] = _ratio(
            sum(m["newcomers_introduced"] for m in measured), sum(m["newcomers"] for m in measured)
        )
    else:
        for metric in (
            "session_dangling_rounds",
            "session_multi_question_rate",
            "session_over_limit_runs",
            "session_repeated_handoffs",
            "session_intro_rate",
        ):
            values[metric] = None

    yes = no = 0
    for item_counts in role_item_counts(situations, sessions).values():
        yes += item_counts.get("yes", 0)
        no += item_counts.get("no", 0)
    values["role_pass_rate"] = _ratio(yes, yes + no)
    return values


def evaluate_targets(
    values: dict[str, float | None], targets: list[Target]
) -> list[dict[str, Any]]:
    """Compara cada métrica com a meta: `ok`, `falhou`, ou `sem dados` quando a camada não rodou."""
    rows = []
    for target in targets:
        value = values.get(target.metric)
        if value is None:
            status = "sem dados"
        elif target.direction == "min":
            status = "ok" if value >= target.goal else "falhou"
        else:
            status = "ok" if value <= target.goal else "falhou"
        rows.append(
            {
                "metric": target.metric,
                "label": target.label,
                "goal": target.goal,
                "direction": target.direction,
                "value": value,
                "status": status,
            }
        )
    return rows
