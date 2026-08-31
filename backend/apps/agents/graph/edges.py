from apps.agents.graph.state import ScenarioState

EXIT_WORDS = ["goodbye", "quit", "exit", "stop the session"]


def student_left(state: ScenarioState) -> str:
    """Roteamento após `listen`: o aluno pediu para encerrar, ou a entrada acabou?"""
    if state.get("should_end"):
        return "end"
    messages = list(state["messages"])
    if messages:
        last = (messages[-1].content or "").lower()
        if any(word in last for word in EXIT_WORDS):
            return "end"
    return "continue"


def make_scene_ended(max_turns: int):
    """Roteamento após `persona`: a cena foi resolvida, ou os turnos se esgotaram?"""

    def scene_ended(state: ScenarioState) -> str:
        if state.get("scene_resolved"):
            return "end"
        if state.get("turn_count", 0) >= max_turns:
            return "end"
        return "continue"

    return scene_ended
