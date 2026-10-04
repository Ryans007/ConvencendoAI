from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from apps.agents.graph.state import ScenarioState
from apps.agents.services.transcript import AFTER_HINT_KEY


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

    A retomada também pode vir como `{"text": ..., "after_hint": True}`, quando o aluno viu
    uma dica naquela vez: a marca fica na mensagem, para o avaliador pesar a autonomia.
    """
    text, after_hint = "", False
    while not text:
        resumed = interrupt(None)
        if isinstance(resumed, dict):
            text = (resumed.get("text") or "").strip()
            after_hint = bool(resumed.get(AFTER_HINT_KEY))
        else:
            text, after_hint = (resumed or "").strip(), False

    marks = {AFTER_HINT_KEY: True} if after_hint else {}
    return {
        "messages": [HumanMessage(content=text, additional_kwargs=marks)],
        "turn_count": state.get("turn_count", 0) + 1,
    }
