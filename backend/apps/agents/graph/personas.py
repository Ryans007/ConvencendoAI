from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from apps.agents.graph.state import ScenarioState
from apps.agents.services.adaptation import adaptation_hint
from apps.agents.services.model_input import conversation_messages
from apps.agents.services.participation import scene_participation
from apps.agents.services.personas import (
    build_system_prompt,
    fallback_line,
    generate_closing_hint_turn,
    generate_closing_line,
    sanitize_line,
)
from apps.agents.services.schemas import PersonaTurn
from apps.agents.services.scenario_content import Role, ScenarioContent
from apps.catalog.models.level import HintPolicy
from apps.llm.constants import ModelPurpose
from apps.llm.services.factory import get_structured_llm


def _fallback_key(content: ScenarioContent, state: ScenarioState) -> str:
    return state.get("current_speaker") or content.role_keys()[0]


def _speak(role: Role, text: str) -> None:
    print(f"{role.name}: {text}")


def _generate_turn(
    llm, messages: list, role: Role, history: list
) -> tuple[PersonaTurn, str, str]:
    """Gera a fala da persona; se vier vazia, tenta uma vez mais e depois usa o fallback.

    Medido em teste real: a fala vazia vem do modelo preenchendo o schema com `line`
    vazio, não de resposta sem schema — por isso a nova tentativa fica aqui, e não só
    na fábrica. Devolve o turno, o texto a falar e o `pass_to` efetivo, que é
    `"student"` quando o fallback é usado, porque uma fala de fallback nunca passa a vez.
    """
    for attempt in range(2):
        turn = llm.invoke(messages)
        text = sanitize_line(turn.line)
        if text:
            return turn, text, turn.pass_to
        print(f"[warning] {role.name} returned an empty line (attempt {attempt + 1}).")
    print(f"[warning] {role.name}: using fallback line.")
    return turn, fallback_line(role, history), "student"


def _show_hint(content: ScenarioContent, hint: str, struggling: bool) -> None:
    """Imprime a dica de contexto na tela (nunca é falada)."""
    hint = (hint or "").strip()
    if not hint:
        return
    if content.hints_policy == HintPolicy.NEVER:
        return
    if content.hints_policy == HintPolicy.WHEN_STUCK and not struggling:
        return
    print(f"    (hint: {hint})")


def make_opening_node(content: ScenarioContent, memory: str):
    """Nó de abertura: a primeira persona inicia a cena.

    Evita a paralisia da primeira frase (o aluno não precisa puxar assunto) e
    força listening desde o começo.
    """
    key = content.role_keys()[0]

    def node_opening(state: ScenarioState) -> dict:
        role = content.role(key)
        system = build_system_prompt(content, role, memory)
        instruction = (
            "Open the scene: say the one line that starts this interaction. "
            'Set scene_resolved to false and pass_to to "student".'
        )

        llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        turn = llm.invoke([SystemMessage(content=system), HumanMessage(content=instruction)])

        text = sanitize_line(turn.line) or "Hello. Let's get started."
        _speak(role, text)
        _show_hint(content, turn.hint, struggling=True)

        return {
            "messages": [AIMessage(content=f"[{role.name}] {text}")],
            "current_speaker": key,
        }

    return node_opening


def make_persona_node(content: ScenarioContent, memory: str):
    """Nó que faz o papel da vez responder, falar e decidir o próximo passo.

    - Na última fala do cenário, a persona encerra em vez de perguntar, senão a sessão
      termina com uma pergunta no ar.
    - Dois turnos antes do fim, a cena abre a oportunidade para os próprios critérios,
      uma vez só.
    - Na passagem de vez, o outro personagem entra na mesma rodada. Se ele só falasse
      na rodada seguinte, a fala da persona atual seria apenas um aviso de troca, e o
      aluno ficaria sem nada para responder.
    - Quando o equilíbrio de turno entrega a vez (`taking_over`), a persona que entra
      recebe a instrução de reagir à resposta do aluno e perguntar, e a passagem de vez
      dela nessa fala é ignorada: senão o aluno poderia ficar sem pergunta na rodada. A
      marca é desligada depois da fala.
    """
    keys = content.role_keys()
    max_turns = content.max_turns

    def node_persona(state: ScenarioState) -> dict:
        key = _fallback_key(content, state)
        role = content.role(key)

        history = list(state["messages"])
        adaptation_line = adaptation_hint(history)
        struggling = bool(adaptation_line)
        taking_over = bool(state.get("taking_over"))

        if state.get("turn_count", 0) >= max_turns:
            text = generate_closing_line(content, role, history)
            _speak(role, text)
            return {
                "messages": [AIMessage(content=f"[{role.name}] {text}")],
                "current_speaker": key,
                "scene_resolved": True,
                "taking_over": False,
            }

        if state.get("turn_count", 0) == max_turns - 2 and content.closing_hint:
            text, hint = generate_closing_hint_turn(content, role, history)
            if text:
                _speak(role, text)
                _show_hint(content, hint, struggling)
                return {
                    "messages": [AIMessage(content=f"[{role.name}] {text}")],
                    "current_speaker": key,
                    "taking_over": False,
                }

        participation = scene_participation(content, key, history)
        system = build_system_prompt(
            content, role, memory, adaptation_line, participation, taking_over=taking_over
        )
        messages = conversation_messages(system, history)

        llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        turn, text, pass_to = _generate_turn(llm, messages, role, history)
        if taking_over and pass_to in keys:
            print(f"[routing] {role.name} acabou de assumir; passagem de vez ignorada")
            pass_to = "student"

        _speak(role, text)
        print(
            f"[routing] current_speaker={key} pass_to={pass_to} "
            f"scene_resolved={turn.scene_resolved}"
        )

        lines = [AIMessage(content=f"[{role.name}] {text}")]
        pending_hint = turn.hint
        resolved = turn.scene_resolved

        next_key = pass_to
        if next_key in keys and next_key != key and not resolved:
            other = content.role(next_key)
            other_participation = scene_participation(content, next_key, history + lines)
            other_system = build_system_prompt(
                content, other, memory, adaptation_line, other_participation
            )
            other_llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
            other_turn, other_text, other_pass_to = _generate_turn(
                other_llm, conversation_messages(other_system, history + lines), other, history
            )
            _speak(other, other_text)
            lines.append(AIMessage(content=f"[{other.name}] {other_text}"))
            pending_hint = other_turn.hint or pending_hint
            resolved = resolved or other_turn.scene_resolved
            print(
                f"[routing] handoff current_speaker={next_key} "
                f"pass_to={other_pass_to} scene_resolved={resolved}"
            )
            if other_pass_to in keys:
                next_key = other_pass_to
        else:
            next_key = next_key if next_key in keys else key

        _show_hint(content, pending_hint, struggling)
        print(f"[routing] next round current_speaker={next_key}")

        return {
            "messages": lines,
            "current_speaker": next_key,
            "scene_resolved": resolved,
            "taking_over": False,
        }

    return node_persona
