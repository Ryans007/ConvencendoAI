from typing import Any

from apps.agents.evaluation.router_layer import summarize_router
from apps.agents.evaluation.schemas import ROLE_ITEMS

_COUNT_METRICS = ("_rounds", "_runs")
_STATUS_MARK = {"ok": "✔", "falhou": "✘", "sem dados": "—"}
_CHECK_TEXT = {
    "passes_to": "passa a vez à persona esperada",
    "no_handoff": "não passa a vez",
    "introduces": "a persona que entra se apresenta",
    "single_question": "uma pergunta só ao aluno",
    "last_line_to_student": "a última fala é dirigida ao aluno",
    "scene_resolved": "estado de cena resolvida como esperado",
    "next_speaker": "a próxima persona da vez é a esperada",
}
MAX_EXAMPLES = 3


def _format(metric: str, value: float | None) -> str:
    if value is None:
        return "—"
    if metric.endswith(_COUNT_METRICS):
        return str(int(value))
    return f"{value:.0%}"


def _scorecard(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| | Métrica | Meta | Resultado |", "|---|---|---|---|"]
    for row in rows:
        sign = "≥" if row["direction"] == "min" else "≤"
        goal = _format(row["metric"], row["goal"])
        lines.append(
            f"| {_STATUS_MARK[row['status']]} | {row['label']} | {sign} {goal} "
            f"| {_format(row['metric'], row['value'])} |"
        )
    return lines


def _router_section(router: list[dict[str, Any]]) -> list[str]:
    summary = summarize_router(router)
    named, wrong = summary["named_correct"], summary["answer_wrong"]
    lines = [
        "## Roteador",
        "",
        f"- Falas que chamam uma persona pelo nome: {named} de {summary['named_total']} certas.",
        f"- Falas que só respondem: {wrong} de {summary['answer_total']} vistas como chamado.",
    ]
    if summary["failed_calls"]:
        lines.append(f"- **{summary['failed_calls']} decisões falharam** e ficaram fora da conta.")
    if summary["errors"]:
        lines += ["", "Erros:", ""]
        for error in summary["errors"]:
            lines.append(
                f"- {error['id']} (vez de {error['current']}): \"{error['line']}\" → "
                f"esperado {error['accepted']}, obtido `{error['routed']}`"
            )
    if summary["ambiguous"]:
        lines += ["", "Casos ambíguos (fora da conta):", ""]
        for case in summary["ambiguous"]:
            lines.append(f"- {case['id']}: \"{case['line']}\" → `{case['routed']}`")
    return lines + [""]


def _situation_section(situations: list[dict[str, Any]]) -> list[str]:
    lines = ["## Situações fixas", ""]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in situations:
        grouped.setdefault(sample["situation"], []).append(sample)
    for situation_id, samples in grouped.items():
        lines.append(f"### {situation_id}")
        errors = [s for s in samples if s["error"]]
        good = [s for s in samples if not s["error"]]
        if errors:
            lines.append(f"- **{len(errors)} amostra(s) falharam ao gerar:** {errors[0]['error']}")
        checks: dict[str, list[bool]] = {}
        questions: dict[str, list[dict[str, Any]]] = {}
        for sample in good:
            for item in sample["expectations"]:
                if item["check"] == "judge":
                    questions.setdefault(item["question"], []).append(item)
                elif item["ok"] is not None:
                    checks.setdefault(item["check"], []).append(item["ok"])
        for check, results in checks.items():
            lines.append(f"- {_CHECK_TEXT.get(check, check)}: {sum(results)} de {len(results)}")
        for question, answers in questions.items():
            confirmed = sum(1 for a in answers if a.get("ok"))
            lines.append(f"- {question} {confirmed} de {len(answers)}")
        failing = [
            s for s in good if any(item["ok"] is False for item in s["expectations"])
        ][:MAX_EXAMPLES]
        for sample in failing:
            lines.append(f"  - exemplo que falhou: {' / '.join(sample['round'])}")
        lines.append("")
    return lines


def _transcript(session: dict[str, Any]) -> list[str]:
    body = [f"    {line}" for line in session["transcript"]]
    return ["<details><summary>Transcrição</summary>", "", *body, "", "</details>"]


def _session_section(sessions: list[dict[str, Any]]) -> list[str]:
    lines = ["## Sessões completas (aluno simulado)", ""]
    for session in sessions:
        lines.append(f"### {session['session']}")
        if session["error"]:
            lines += [f"- **A sessão falhou:** {session['error']}", ""]
            continue
        metrics = session["metrics"]
        state = "cena resolvida" if session["scene_resolved"] else "limite de turnos"
        lines += [
            f"- Terminou por: {state} ({session['turn_count']} de {session['max_turns']} turnos).",
            f"- Falas por persona: {metrics['lines_by_persona']}.",
            f"- Quem fechou cada rodada: {' '.join(metrics['leaders'])}.",
            f"- Trocas de condução: {metrics['changes']}, por: {metrics['causes'] or 'nenhuma'}.",
            f"- Maior sequência da mesma persona: {metrics['max_run']} "
            f"(acima do máximo do cenário: {metrics['over_limit_runs']}).",
            f"- Rodadas com mais de uma pergunta: {metrics['multi_question_rounds']}.",
            f"- Apresentações na primeira fala: {metrics['introduced']}.",
        ]
        for line in metrics["dangling_rounds"]:
            lines.append(f"- **Rodada terminando dirigida a outra persona:** {line}")
        lines += ["", *_transcript(session), ""]
    return lines


def _role_section(
    role_items: dict[str, dict[str, int]], failing: list[dict[str, str]]
) -> list[str]:
    lines = [
        "## Papel das personas (juiz)",
        "",
        "| Item | Sim | Não | Não se aplica |",
        "|---|---|---|---|",
    ]
    for item, (label, _) in ROLE_ITEMS.items():
        counts = role_items.get(item, {})
        lines.append(
            f"| {label} | {counts.get('yes', 0)} | {counts.get('no', 0)} | {counts.get('na', 0)} |"
        )
    if failing:
        lines += ["", "Falas que falharam em algum item:", ""]
        for failure in failing:
            lines.append(f"- **{failure['label']}** — {failure['line']} — _{failure['reason']}_")
    return lines + [""]


def failing_role_lines(
    situations: list[dict[str, Any]], sessions: list[dict[str, Any]], limit: int = 15
) -> list[dict[str, str]]:
    """As falas que o juiz reprovou em algum item, com o item e o motivo, até `limit`."""
    failures = []
    for source in (*situations, *sessions):
        for judged in source.get("roles", []):
            for item, verdict in judged.get("items", {}).items():
                if verdict["answer"] == "no":
                    failures.append(
                        {
                            "label": ROLE_ITEMS[item][0],
                            "line": judged["line"],
                            "reason": verdict["reason"],
                        }
                    )
    return failures[:limit]


def _usage_section(usage: dict[str, Any]) -> list[str]:
    lines = [
        "## Consumo",
        "",
        "| Papel | Modelo | Chamadas | Tokens de entrada | Tokens de saída |",
        "|---|---|---|---|---|",
    ]
    for row in usage["by_purpose"]:
        lines.append(
            f"| {row['purpose']} | {row['model']} | {row['calls']} "
            f"| {row['input_tokens']} | {row['output_tokens']} |"
        )
    latency = usage.get("persona_latency")
    if latency:
        lines += [
            "",
            f"Tempo por chamada da persona: mediana {latency['median_s']:.2f} s, "
            f"90% das chamadas abaixo de {latency['p90_s']:.2f} s ({latency['count']} chamadas).",
        ]
    lines.append(
        f"Custo estimado: US$ {usage['cost_usd']:.4f}"
        + (f" ({usage['unpriced']} chamadas sem preço cadastrado)." if usage["unpriced"] else ".")
    )
    return lines + [""]


def _overridden_note(overridden: list[str]) -> str:
    if not overridden:
        return ""
    return f" (trocados só nesta execução: {', '.join(overridden)})"


def build_report(run: dict[str, Any]) -> str:
    """Monta o relatório em português: placar, camadas, papel, consumo e o que ler primeiro."""
    models = ", ".join(f"{purpose}: {model}" for purpose, model in run["models"].items())
    lines = [
        f"# Avaliação da conversa — {run['label']}",
        "",
        f"- Início: {run['started_at']} | Fim: {run['finished_at']}",
        f"- Camadas: {', '.join(run['layers'])} | "
        f"Chamadas no máximo previstas: {run['calls_estimated']}",
        f"- Modelos: {models}" + _overridden_note(run["overridden"]),
        "- As sessões usam um aluno simulado: ele fala melhor que um aluno real, e as amostras "
        "são pequenas. Use os números para comparar o antes e o depois.",
        "",
        "## Placar",
        "",
        *_scorecard(run["scorecard"]),
        "",
    ]
    if "router" in run["layers"]:
        lines += _router_section(run["router"])
    if "situations" in run["layers"]:
        lines += _situation_section(run["situations"])
    if "sessions" in run["layers"]:
        lines += _session_section(run["sessions"])
    if run["use_judge"]:
        lines += _role_section(
            run["role_items"], failing_role_lines(run["situations"], run["sessions"])
        )
    lines += _usage_section(run["usage"])
    return "\n".join(lines).rstrip() + "\n"
