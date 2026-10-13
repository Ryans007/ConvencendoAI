from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.evaluation import judge
from apps.agents.evaluation.case_loader import StudentProfile
from apps.agents.evaluation.metrics import session_metrics, speaker_and_text
from apps.agents.evaluation.output import captured_output
from apps.agents.evaluation.simulated_student import SimulatedStudent
from apps.agents.graph.builder import build_scenario_graph
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import ScenarioContent

RECURSION_LIMIT = 200


def transcript_lines(messages: list) -> list[str]:
    """A transcrição como "[Nome] fala" para personas e "Student: fala" para o aluno."""
    return [
        f"Student: {message.content}" if isinstance(message, HumanMessage) else message.content
        for message in messages
    ]


def _judge_persona_lines(content: ScenarioContent, messages: list) -> list[dict[str, Any]]:
    role_by_name = {role.name: role for role in content.roles}
    results = []
    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue
        parsed = speaker_and_text(message.content)
        role = role_by_name.get(parsed[0]) if parsed else None
        if role is None:
            continue
        try:
            items = judge.judge_line(content, role, messages[:index], message.content)
            results.append({"line": message.content, "items": items, "error": ""})
        except judge.JudgeFailed as exc:
            results.append({"line": message.content, "items": {}, "error": str(exc)})
    return results


def run_session_layer(
    profiles: list[StudentProfile],
    contents: dict[tuple[str, int], ScenarioContent],
    *,
    use_judge: bool = True,
    progress: Callable[[str], None] = lambda message: None,
) -> list[dict[str, Any]]:
    """Roda uma sessão completa por perfil, com o aluno simulado e o grafo real.

    A sessão termina como uma real (cena resolvida ou limite de turnos). Cada resultado guarda
    a transcrição, os eventos de cada rodada, as métricas de troca e, com o juiz ligado, a lista
    de verificação de cada fala de persona. Uma falha numa sessão fica registrada nela.
    """
    results = []
    for profile in profiles:
        content = contents[(profile.scenario, profile.level)]
        student = SimulatedStudent(content, profile)
        graph = build_scenario_graph(content, "", listen_node=student.listen)
        initial = {
            "messages": [],
            "current_speaker": "",
            "turn_count": 0,
            "scene_resolved": False,
            "should_end": False,
            "taking_over": False,
            "addressed_by_student": False,
        }
        entry: dict[str, Any] = {
            "session": profile.id,
            "scenario": profile.scenario,
            "level": profile.level,
            "max_turns": content.max_turns,
            "error": "",
        }
        try:
            with captured_output(), collect_round_events() as events:
                final = graph.invoke(initial, config={"recursion_limit": RECURSION_LIMIT})
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            results.append(entry)
            continue
        messages = list(final["messages"])
        transcript = transcript_lines(messages)
        entry.update(
            {
                "transcript": transcript,
                "events": events,
                "scene_resolved": bool(final.get("scene_resolved")),
                "turn_count": final.get("turn_count", 0),
                "metrics": session_metrics(transcript, events, content),
                "roles": _judge_persona_lines(content, messages) if use_judge else [],
            }
        )
        results.append(entry)
        progress(f"sessão: {profile.id}")
    return results
