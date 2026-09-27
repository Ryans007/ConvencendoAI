from langchain_core.messages import SystemMessage

from apps.agents.graph.state import ScenarioState
from apps.agents.services.schemas import RoutingDecision
from apps.agents.services.scenario_content import ScenarioContent
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import ModelNotConfigured, get_structured_llm

_ROUTING_PROMPT = """You are deciding which character should respond to the student next,
in a role-play conversation with {roster}.

The character currently expected to respond is "{current}".

Look ONLY at the student's most recent message. If it clearly addresses one specific
character by name, or clearly continues a topic only that character raised, answer with
that character's key. Otherwise — including when you are not sure — answer with
"{current}", the character already expected to respond.

Answer with exactly one of: {valid_keys}."""


def make_routing_node(content: ScenarioContent):
    """Nó entre `listen` e `persona`: confere se o aluno se dirigiu a uma persona
    específica, e sobrescreve quem responde quando for o caso.

    Sem modelo de roteamento configurado, ou se a chamada falhar por qualquer motivo,
    o nó não altera nada — é um refinamento sobre o roteamento padrão, nunca um
    requisito para a execução continuar.
    """
    keys = content.role_keys()

    def node_routing(state: ScenarioState) -> dict:
        if len(keys) < 2:
            return {}

        current = state.get("current_speaker") or keys[0]
        roster = ", ".join(f"{content.role(key).name} (key: {key})" for key in keys)
        system = _ROUTING_PROMPT.format(
            roster=roster,
            current=current,
            valid_keys=" | ".join(f'"{key}"' for key in keys),
        )

        try:
            llm = get_structured_llm(ModelPurpose.ROUTER, RoutingDecision)
            decision = llm.invoke([SystemMessage(content=system)] + list(state["messages"]))
        except ModelNotConfigured:
            return {}
        except Exception as exc:
            print(f"[routing] falha ao decidir roteamento, mantendo {current}: {exc}")
            return {}

        if decision.speaker in keys and decision.speaker != current:
            print(f"[routing] aluno direcionou para {decision.speaker} (era {current})")
            return {"current_speaker": decision.speaker}
        return {}

    return node_routing
