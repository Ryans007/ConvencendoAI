from langchain_core.messages import HumanMessage

from apps.agents.graph.state import ScenarioState


def listen(state: ScenarioState) -> dict:
    """Nó do grafo: captura o turno do aluno por texto, via entrada bloqueante de terminal."""
    try:
        text = input("\nYou (in English): ").strip()
    except (EOFError, KeyboardInterrupt):
        return {"turn_count": state.get("turn_count", 0), "should_end": True}

    if not text:
        return {"turn_count": state.get("turn_count", 0) + 1, "should_end": True}

    return {
        "messages": [HumanMessage(content=text)],
        "turn_count": state.get("turn_count", 0) + 1,
    }
