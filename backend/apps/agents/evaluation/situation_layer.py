from collections.abc import Callable
from typing import Any

from apps.agents.evaluation import judge
from apps.agents.evaluation.case_loader import Expectation, Situation
from apps.agents.evaluation.metrics import (
    introduces_self,
    is_addressed_to_another,
    question_count,
    speaker_and_text,
)
from apps.agents.evaluation.output import captured_output
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import ScenarioContent


def _round_end(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next((event for event in reversed(events) if event["kind"] == "round_end"), {})


def check_structural(
    expectation: Expectation,
    round_lines: list[str],
    events: list[dict[str, Any]],
    content: ScenarioContent,
) -> bool:
    """Confere, pelo código, uma expectativa estrutural sobre a rodada gerada."""
    names = [role.name for role in content.roles]
    check, value = expectation.check, expectation.value
    if check == "passes_to":
        return any(e["kind"] == "handoff" and e["target"] == value for e in events)
    if check == "no_handoff":
        return not any(e["kind"] == "handoff" for e in events)
    if check == "single_question":
        return question_count(round_lines) <= 1
    if check == "last_line_to_student":
        last = speaker_and_text(round_lines[-1]) if round_lines else None
        return bool(last) and not is_addressed_to_another(round_lines[-1], last[0], names)
    if check == "introduces":
        name = content.role(value).name
        return any(
            introduces_self(parsed[1], name)
            for parsed in (speaker_and_text(line) for line in round_lines)
            if parsed and parsed[0] == name
        )
    if check == "scene_resolved":
        return bool(_round_end(events).get("scene_resolved", False)) == value
    if check == "next_speaker":
        return _round_end(events).get("next_speaker") == value
    if check == "speaker":
        first = speaker_and_text(round_lines[0]) if round_lines else None
        return bool(first) and first[0] == content.role(value).name
    raise ValueError(f"Verificação desconhecida: {check}")


def _sample_state(situation: Situation) -> dict[str, Any]:
    return {
        "messages": list(situation.history),
        "current_speaker": situation.current,
        "turn_count": situation.turn_count,
        "taking_over": situation.taking_over,
        "addressed_by_student": situation.addressed,
        "scene_resolved": False,
        "should_end": False,
    }


def run_situation_layer(
    situations: list[Situation],
    contents: dict[tuple[str, int], ScenarioContent],
    *,
    samples: int | None = None,
    use_judge: bool = True,
    progress: Callable[[str], None] = lambda message: None,
) -> list[dict[str, Any]]:
    """Gera a rodada de cada situação várias vezes com o nó real da persona e confere o esperado.

    Cada amostra guarda as falas, os eventos, o resultado de cada expectativa e, com o juiz
    ligado, o veredito das perguntas semânticas e da lista de verificação de cada fala. Uma
    falha ao gerar a rodada fica registrada na amostra, sem interromper as demais.
    """
    results = []
    for situation in situations:
        content = contents[(situation.scenario, situation.level)]
        node = make_persona_node(content, memory="")
        for sample in range(samples or situation.samples):
            entry: dict[str, Any] = {"situation": situation.id, "sample": sample, "error": ""}
            try:
                with captured_output(), collect_round_events() as events:
                    out = node(_sample_state(situation))
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                results.append(entry)
                continue
            round_lines = [message.content for message in out["messages"]]
            entry.update(
                {
                    "context": judge.context_lines(situation.history, limit=None),
                    "round": round_lines,
                    "events": events,
                    "expectations": [],
                    "roles": [],
                }
            )
            for expectation in situation.expectations:
                if expectation.check == "judge":
                    if not use_judge:
                        continue
                    try:
                        verdict = judge.judge_question(
                            expectation.judge, situation.history, round_lines
                        )
                        entry["expectations"].append(
                            {
                                "check": "judge",
                                "question": expectation.judge,
                                **verdict,
                                "ok": verdict["answer"] == "yes",
                            }
                        )
                    except judge.JudgeFailed as exc:
                        entry["expectations"].append(
                            {
                                "check": "judge",
                                "question": expectation.judge,
                                "error": str(exc),
                                "ok": None,
                            }
                        )
                else:
                    entry["expectations"].append(
                        {
                            "check": expectation.check,
                            "value": expectation.value,
                            "ok": check_structural(expectation, round_lines, events, content),
                        }
                    )
            if use_judge:
                entry["roles"] = judge.judge_round(content, situation.history, round_lines)
            results.append(entry)
        progress(f"situação: {situation.id}")
    return results
