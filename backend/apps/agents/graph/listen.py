from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from apps.agents.graph.state import ScenarioState


def listen(state: ScenarioState) -> dict:
    """Nó do grafo: captura o turno do aluno por texto, via entrada bloqueante de terminal.

    Linha vazia pede a fala de novo, em vez de encerrar a sessão. Só o fim da entrada
    (EOF) encerra.
    """
    text = ""
    while not text:
        try:
            text = input("\nYou (in English): ").strip()
        except (EOFError, KeyboardInterrupt):
            return {"turn_count": state.get("turn_count", 0), "should_end": True}

    return {
        "messages": [HumanMessage(content=text)],
        "turn_count": state.get("turn_count", 0) + 1,
    }


def listen_live(state: ScenarioState) -> dict:
    """Nó do grafo: pausa e aguarda o turno do aluno já transcrito, via voz.

    Quem retoma a execução (`Command(resume=texto)`) é o consumer da sessão ao vivo,
    depois de transcrever o áudio recebido pelo WebSocket — este nó não sabe que existe
    voz, só que alguém vai lhe entregar o texto do turno de fora. Um turno vazio nunca
    encerra a sessão: o nó volta a pausar e espera outro.
    """
    text = ""
    while not text:
        text = (interrupt(None) or "").strip()

    return {
        "messages": [HumanMessage(content=text)],
        "turn_count": state.get("turn_count", 0) + 1,
    }
