from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from apps.agents.graph.state import ScenarioState
from apps.agents.services.adaptation import adaptation_hint
from apps.agents.services.model_input import conversation_messages
from apps.agents.services.participation import scene_participation
from apps.agents.services.round_trace import record_round_event
from apps.agents.services.personas import (
    build_system_prompt,
    fallback_line,
    generate_closing_hint_line,
    generate_closing_line,
    sanitize_line,
)
from apps.agents.services.schemas import PersonaTurn
from apps.agents.services.scenario_content import Role, ScenarioContent
from apps.llm.constants import ModelPurpose
from apps.llm.services.conversation_log import conversation_log
from apps.llm.services.factory import get_structured_llm


def _fallback_key(content: ScenarioContent, state: ScenarioState) -> str:
    return state.get("current_speaker") or content.role_keys()[0]


def _speak(role: Role, text: str) -> None:
    conversation_log(role.name, text)


def _generate_turn(
    llm, messages: list, role: Role, history: list
) -> tuple[PersonaTurn, str, bool]:
    """Gera a fala da persona; se vier vazia, tenta uma vez mais e depois usa o fallback.

    Medido em teste real: a fala vazia vem do modelo preenchendo o schema com `line`
    vazio, não de resposta sem schema — por isso a nova tentativa fica aqui, e não só
    na fábrica. Devolve o turno, o texto a falar e se foi usado o fallback: uma fala de
    fallback é uma pergunta ao aluno e nunca passa a vez, então o chamador não a faz seguir
    de uma passagem de vez.
    """
    for attempt in range(2):
        turn = llm.invoke(messages)
        text = sanitize_line(turn.line)
        if text:
            return turn, text, False
        print(f"[warning] {role.name} returned an empty line (attempt {attempt + 1}).")
    print(f"[warning] {role.name}: using fallback line.")
    return turn, fallback_line(role, history), True


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
        record_round_event("opening", speaker=key)

        return {
            "messages": [AIMessage(content=f"[{role.name}] {text}")],
            "current_speaker": key,
        }

    return node_opening


def final_speaker(content: ScenarioContent, role: Role) -> Role:
    """Quem diz as falas finais: a persona da vez, se ela decide; senão, a primeira que decide."""
    if content.decides(role.key):
        return role
    return content.deciders()[0]


def _accepted_resolution(content: ScenarioContent, role: Role, resolved: bool) -> bool:
    """Só vale a cena resolvida indicada por um papel que decide; as outras são registradas."""
    if resolved and not content.decides(role.key):
        print(f"[routing] {role.name} nao decide a cena; cena resolvida ignorada")
        record_round_event("resolution_ignored", speaker=role.key)
        return False
    return resolved


def make_persona_node(content: ScenarioContent, memory: str):
    """Nó que faz o papel da vez responder e falar, e que fecha a rodada.

    - Na última fala do cenário, a persona encerra em vez de perguntar, senão a sessão
      termina com uma pergunta no ar.
    - Dois turnos antes do fim, a cena abre a oportunidade para os próprios critérios,
      uma vez só.
    - A passagem de vez é decidida pelo diretor de cena, não pela persona: o `pass_to` que
      ela devolve é ignorado e fica no registro como `handoff_ignored`. Só há passagem quando
      o aluno chamou uma persona para o assunto de outro personagem (`redirect_to`): a
      persona chamada diz numa frase que é com ele, e ele entra na mesma rodada, responde e
      pergunta. Se ele só falasse na rodada seguinte, a fala da persona chamada seria apenas
      um aviso de troca, e o aluno ficaria sem nada para responder. Uma fala de fallback nunca
      é seguida de passagem de vez.
    - Quando o equilíbrio de turno ou o assunto entrega a vez (`taking_over`), a persona que
      entra recebe a instrução de reagir à resposta do aluno e perguntar. A marca é
      desligada depois da fala.
    - Quando o aluno chamou a persona (`addressed_by_student`), ela responde ao que ele
      disse e fecha a rodada. A marca também é desligada depois da fala, em todos os
      caminhos de saída, e `redirect_to` junto com ela.
    - Quando a persona resolve a cena (`scene_resolved`), a sessão termina logo depois da
      fala, então uma pergunta nela ficaria sem resposta. O prompt completo manda perguntar
      em toda rodada e manda fechar a interação, e o modelo obedece às duas: marca a cena
      como resolvida e pergunta mesmo assim. Por isso, se a última fala da rodada tem
      pergunta, ela é trocada pelo fechamento do limite de turnos, que usa um prompt próprio
      que proíbe pergunta.

    - Só um papel que decide o resultado da cena (`decides_outcome`) encerra a cena como
      resolvida e diz as falas finais. Um aliado que indica `scene_resolved` é ignorado, e o
      evento `resolution_ignored` fica no registro: medido numa negociação, o aliado
      confirmava um prazo que só a PM podia conceder. A fala que abre a oportunidade dos
      critérios e o fechamento do limite de turnos são ditos por `final_speaker`: a persona
      da vez, se ela decide, ou a primeira que decide pela ordem de abertura.
    """
    keys = content.role_keys()
    max_turns = content.max_turns

    def node_persona(state: ScenarioState) -> dict:
        key = _fallback_key(content, state)
        role = content.role(key)

        history = list(state["messages"])
        adaptation_line = adaptation_hint(history)
        taking_over = bool(state.get("taking_over"))
        addressed = bool(state.get("addressed_by_student"))
        redirect_key = state.get("redirect_to") or ""
        redirect_role = (
            content.role(redirect_key) if redirect_key in keys and redirect_key != key else None
        )

        if state.get("turn_count", 0) >= max_turns:
            final_role = final_speaker(content, role)
            text = generate_closing_line(content, final_role, history)
            _speak(final_role, text)
            record_round_event("closing", speaker=final_role.key)
            return {
                "messages": [AIMessage(content=f"[{final_role.name}] {text}")],
                "current_speaker": final_role.key,
                "scene_resolved": True,
                "taking_over": False,
                "addressed_by_student": False,
                "redirect_to": "",
            }

        if state.get("turn_count", 0) == max_turns - 2 and content.closing_hint:
            final_role = final_speaker(content, role)
            text = generate_closing_hint_line(content, final_role, history)
            if text:
                _speak(final_role, text)
                record_round_event("closing_hint", speaker=final_role.key)
                return {
                    "messages": [AIMessage(content=f"[{final_role.name}] {text}")],
                    "current_speaker": final_role.key,
                    "taking_over": False,
                    "addressed_by_student": False,
                    "redirect_to": "",
                }

        participation = scene_participation(content, key, history)
        system = build_system_prompt(
            content,
            role,
            memory,
            adaptation_line,
            participation,
            taking_over=taking_over,
            addressed_by_student=addressed,
            redirect_to=redirect_role,
        )
        messages = conversation_messages(system, history)

        llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        turn, text, from_fallback = _generate_turn(llm, messages, role, history)
        directed = redirect_role.key if redirect_role else key
        if turn.pass_to in keys and turn.pass_to not in (key, directed):
            print(f"[routing] {role.name} tentou passar a vez; quem decide e o diretor de cena")
            record_round_event("handoff_ignored", speaker=key, reason="director_decides")

        _speak(role, text)
        print(f"[routing] current_speaker={key} scene_resolved={turn.scene_resolved}")

        lines = [AIMessage(content=f"[{role.name}] {text}")]
        speaker = role
        resolved = _accepted_resolution(content, role, turn.scene_resolved)

        next_key = key
        if redirect_role and not from_fallback and not resolved:
            other = redirect_role
            other_participation = scene_participation(content, other.key, history + lines)
            other_system = build_system_prompt(
                content,
                other,
                memory,
                adaptation_line,
                other_participation,
                received_from=role,
            )
            other_llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
            other_turn, other_text, _ = _generate_turn(
                other_llm, conversation_messages(other_system, history + lines), other, history
            )
            _speak(other, other_text)
            record_round_event("handoff", origin=key, target=other.key)
            lines.append(AIMessage(content=f"[{other.name}] {other_text}"))
            speaker = other
            next_key = other.key
            resolved = resolved or _accepted_resolution(
                content, other, other_turn.scene_resolved
            )
            print(f"[routing] passagem de {role.name} para {other.name}; resolved={resolved}")

        if resolved and "?" in lines[-1].content:
            print(
                f"[routing] cena resolvida com pergunta na fala de {speaker.name}; "
                "trocando por fechamento"
            )
            closing = generate_closing_line(content, speaker, history + lines[:-1])
            _speak(speaker, closing)
            record_round_event("closing_swap", speaker=speaker.key)
            lines[-1] = AIMessage(content=f"[{speaker.name}] {closing}")

        print(f"[routing] next round current_speaker={next_key}")
        record_round_event(
            "round_end", speaker=speaker.key, next_speaker=next_key, scene_resolved=resolved
        )

        return {
            "messages": lines,
            "current_speaker": next_key,
            "scene_resolved": resolved,
            "taking_over": False,
            "addressed_by_student": False,
            "redirect_to": "",
        }

    return node_persona
