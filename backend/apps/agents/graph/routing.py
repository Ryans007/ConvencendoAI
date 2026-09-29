import random

from apps.agents.graph.state import ScenarioState
from apps.agents.services.model_input import conversation_messages
from apps.agents.services.participation import scene_participation
from apps.agents.services.schemas import RoutingDecision
from apps.agents.services.scenario_content import ScenarioContent
from apps.agents.services.turn_balance import next_leader, should_hand_over
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import ModelNotConfigured, get_structured_llm

NO_ADDRESSEE = "none"

_ROUTING_PROMPT = """You are deciding whether the student is speaking to one specific
character, in a role-play conversation with {roster}.

Look ONLY at the student's most recent message. Answer with a character's key ONLY if the
student explicitly turns to that character — calling them by name, or clearly speaking to
them instead of to whoever asked last. Simply answering the question that was just asked
is NOT addressing anyone: answer "{none}". Answer "{none}" also whenever you are not sure.

Answer with exactly one of: {valid_keys} | "{none}"."""


def make_routing_node(content: ScenarioContent, rng: random.Random | None = None):
    """Nó entre `listen` e `persona`: decide quem conduz a rodada.

    Primeiro vale a escolha do aluno: quando ele se dirige a uma persona específica, é
    ela quem responde, mesmo que não fosse a vez dela. Sem destinatário, vale o
    equilíbrio: se a persona da vez já conduziu rodadas seguidas demais, a rodada passa a
    outro personagem, e `taking_over` avisa quem entra que é ela quem faz a transição.

    Sem modelo de roteamento configurado, ou se a chamada falhar por qualquer motivo, o
    nó trata como "sem destinatário" — o equilíbrio continua valendo, e a execução nunca
    é interrompida. `rng` é injetável para os testes controlarem o sorteio.
    """
    keys = content.role_keys()
    draw = rng or random.Random()

    def addressed_speaker(state: ScenarioState) -> str | None:
        roster = ", ".join(f"{content.role(key).name} (key: {key})" for key in keys)
        system = _ROUTING_PROMPT.format(
            roster=roster,
            none=NO_ADDRESSEE,
            valid_keys=" | ".join(f'"{key}"' for key in keys),
        )
        try:
            llm = get_structured_llm(ModelPurpose.ROUTER, RoutingDecision)
            decision = llm.invoke(conversation_messages(system, list(state["messages"])))
        except ModelNotConfigured:
            return None
        except Exception as exc:
            print(f"[routing] falha ao decidir roteamento, seguindo sem destinatario: {exc}")
            return None
        return decision.speaker if decision.speaker in keys else None

    def node_routing(state: ScenarioState) -> dict:
        if len(keys) < 2:
            return {}

        current = state.get("current_speaker") or keys[0]
        addressed = addressed_speaker(state)
        if addressed is not None:
            if addressed != current:
                print(f"[routing] aluno direcionou para {addressed} (era {current})")
                return {"current_speaker": addressed, "taking_over": False}
            return {}

        history = list(state["messages"])
        rounds_led = scene_participation(content, current, history).consecutive_rounds_led
        if should_hand_over(rounds_led, content.max_consecutive_turns, draw):
            leader = next_leader(content, current, history)
            print(
                f"[routing] equilibrio: {current} conduziu {rounds_led} rodada(s) seguida(s); "
                f"vez de {leader}"
            )
            return {"current_speaker": leader, "taking_over": True}
        return {}

    return node_routing
