from langgraph.graph import END, START, StateGraph

from apps.agents.graph.edges import make_scene_ended, student_left
from apps.agents.graph.listen import listen
from apps.agents.graph.personas import make_opening_node, make_persona_node
from apps.agents.graph.routing import make_routing_node
from apps.agents.graph.state import ScenarioState
from apps.agents.services.scenario_content import ScenarioContent


def build_scenario_graph(
    content: ScenarioContent,
    memory: str = "",
    *,
    listen_node=listen,
    checkpointer=None,
):
    """Compila o grafo de execução de um cenário. `memory` é o resumo do cenário anterior.

    `listen_node` troca o mecanismo de captura do turno do aluno sem duplicar a montagem
    do grafo — texto usa `listen` (bloqueante em `input()`); voz usa `listen_live`
    (pausa em `interrupt()`, retomada pelo consumer da sessão ao vivo). `checkpointer`
    só é necessário quando o grafo precisa pausar entre chamadas — texto não precisa.
    """
    workflow = StateGraph(ScenarioState)
    workflow.add_node("opening", make_opening_node(content, memory))
    workflow.add_node("listen", listen_node)
    workflow.add_node("routing", make_routing_node(content))
    workflow.add_node("persona", make_persona_node(content, memory))

    workflow.add_edge(START, "opening")
    workflow.add_edge("opening", "listen")
    workflow.add_conditional_edges(
        "listen", student_left, {"continue": "routing", "end": END}
    )
    workflow.add_edge("routing", "persona")
    workflow.add_conditional_edges(
        "persona", make_scene_ended(content.max_turns), {"continue": "listen", "end": END}
    )

    return workflow.compile(checkpointer=checkpointer)


def run_scenario(content: ScenarioContent, memory: str = "") -> dict:
    """Roda um cenário do início ao fim e devolve o estado final."""
    graph = build_scenario_graph(content, memory)
    initial_state: ScenarioState = {
        "messages": [],
        "current_speaker": "",
        "turn_count": 0,
        "scene_resolved": False,
        "should_end": False,
        "taking_over": False,
        "addressed_by_student": False,
    }
    return graph.invoke(initial_state, config={"recursion_limit": 200})
