from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from apps.agents.graph.state import ScenarioState
from apps.agents.services.adaptation import adaptation_hint
from apps.agents.services.dialogue_lines import addressed_persona
from apps.agents.services.line_instruction import line_instruction
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
    """Escreve a fala no log e a anuncia a quem acompanha a execução do grafo em fluxo.

    É chamada uma vez por fala, no instante em que o texto fica definitivo, em todos os caminhos do
    nó, então o consumidor da sessão ao vivo pode falar a primeira fala da rodada sem esperar a
    geração das seguintes. O anúncio é só um aviso: o que o nó devolve no estado continua sendo a
    fonte da conversa, e as execuções que não acompanham o fluxo (texto, avaliador, testes que
    chamam o nó direto) seguem como antes, porque fora de um grafo em fluxo não há para quem avisar.
    """
    conversation_log(role.name, text)
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({"speaker": role.name, "text": text})


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

    A abertura é dita ao aluno: se o modelo a dirige à outra persona pelo vocativo ("Tom, the
    client expects..."), ele tenta de novo uma vez, e se a segunda também vier assim usa uma
    saudação fixa. Medido numa avaliação com o modelo real, 1 de 5 aberturas saía assim e ficava
    sem resposta, porque a guarda da última fala só vale para as rodadas seguintes.
    """
    key = content.role_keys()[0]
    names = [candidate.name for candidate in content.roles]

    def node_opening(state: ScenarioState) -> dict:
        role = content.role(key)
        system = build_system_prompt(content, role, memory)
        instruction = (
            "Open the scene: say the one line that starts this interaction. "
            "Speak to the student, never to anyone else in the scene. "
            'Set pass_to to "student".'
        )

        llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        text = ""
        for attempt in range(2):
            turn = llm.invoke([SystemMessage(content=system), HumanMessage(content=instruction)])
            text = sanitize_line(turn.line)
            if text and addressed_persona(text, role.name, names) is None:
                break
            record_round_event("opening_retried", speaker=key, attempt=attempt + 1)
            text = ""
        text = text or "Hello. Let's get started."
        _speak(role, text)
        record_round_event("opening", speaker=key)

        return {
            "messages": [AIMessage(content=f"[{role.name}] {text}")],
            "current_speaker": key,
        }

    return node_opening


def final_speaker(content: ScenarioContent, role: Role, receiver: Role | None = None) -> Role:
    """Quem diz as falas finais: quem recebe a vez nesta rodada, se decide; senão, a da vez.

    Se a persona da vez não decide, é a primeira que decide. Quando o diretor de cena passou a
    vez a outra persona nesta rodada (`receiver`) e ela decide, é ela quem diz a fala final:
    medido numa sessão real, a Emma respondia sobre o assunto do James na fala da
    oportunidade, porque essa fala ignorava a passagem, e inventava a resposta.
    """
    if receiver is not None and content.decides(receiver.key):
        return receiver
    if content.decides(role.key):
        return role
    return content.deciders()[0]


def make_persona_node(content: ScenarioContent, memory: str):
    """Nó que faz o papel da vez responder e falar, e que fecha a rodada.

    - Na última fala do cenário, a persona encerra em vez de perguntar, senão a sessão
      termina com uma pergunta no ar.
    - Dois turnos antes do fim, a cena abre a oportunidade para os próprios critérios,
      uma vez só.
    - A passagem de vez é decidida pelo diretor de cena, não pela persona: o `pass_to` que
      ela devolve é ignorado e fica no registro como `handoff_ignored`. Há passagem em dois
      casos, os dois com quem recebe falando na mesma rodada, logo depois, para responder e
      perguntar. Se ele só falasse na rodada seguinte, a fala de quem passa seria apenas um
      aviso de troca, e o aluno ficaria sem nada para responder. No primeiro, o aluno chamou
      uma persona para o assunto de outro personagem (`redirect_to`): a persona chamada diz
      numa frase que é com ele. No segundo, o equilíbrio de turno ou o assunto trocou quem
      conduz (`hand_floor_to`): a persona da vez reage ao que o aluno disse e passa a palavra
      ao colega pelo nome. Uma fala de fallback nunca é seguida de passagem de vez.
    - Quando o aluno chamou a persona (`addressed_by_student`), ela responde ao que ele
      disse e fecha a rodada. A marca também é desligada depois da fala, em todos os
      caminhos de saída, e `redirect_to` junto com ela.
    - Uma rodada nunca termina dirigida a outra persona: se a última fala tem o vocativo da
      colega logo no começo, a colega fala em seguida, responde e pergunta ao aluno, no máximo
      uma fala a mais, e o evento `dangling_answered` fica no registro. Se essa fala também
      termina dirigida à outra, a rodada termina assim e `dangling_unresolved` registra a falha.
      Isso cobre os três caminhos em que a persona escrevia para a colega e ninguém respondia:
      a passagem devolvida, a persona que assume pelo equilíbrio ou pelo assunto, e a persona
      chamada pelo aluno.
    - Nenhuma persona encerra a cena: o modelo não tem campo para isso. A cena termina no
      limite de turnos, na fala de fechamento, ou a pedido do aluno, feito fora deste nó. O fechamento e a fala que abre
      a oportunidade dos critérios são ditos por `final_speaker`: a persona que recebe a vez
      nesta rodada, se ela decide, ou a persona da vez, se ela decide, ou a primeira que decide
      pela ordem de abertura. Medido numa negociação, o
      aliado confirmava um prazo que só a PM podia conceder.
    - Numa cena com coadjuvante, `supporting_enters` monta a rodada dele: em `first` ele fala
      antes, sem pergunta, e a persona da vez fecha; em `after` a persona chamada pelo aluno
      responde sem pergunta e ele fecha com uma pergunta curta. Quando ele recebe a passagem
      pelo assunto ou o vocativo de uma principal, também fecha com uma pergunta curta. Em
      todos os casos a persona da vez na rodada seguinte é uma principal, e a rodada tem no
      máximo duas falas: um vocativo que sobraria para uma terceira fala fica registrado como
      `dangling_unresolved`.
    """
    keys = content.role_keys()
    max_turns = content.max_turns

    def _follow_up_line(
        other: Role, previous: Role, so_far: list, adaptation_line: str
    ) -> AIMessage:
        """Gera e fala a fala de `other` logo depois de `previous`, na mesma rodada."""
        prompt_marks = (
            {"supporting_closes_after": previous}
            if other.supporting
            else {"received_from": previous}
        )
        participation = scene_participation(content, other.key, so_far)
        other_system = build_system_prompt(
            content, other, memory, adaptation_line, participation, **prompt_marks
        )
        instruction = line_instruction(other, participation, **prompt_marks)
        other_llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        _, other_text, _ = _generate_turn(
            other_llm, conversation_messages(other_system, so_far, instruction), other, so_far
        )
        _speak(other, other_text)
        return AIMessage(content=f"[{other.name}] {other_text}")

    def supporting_first_round(leader: Role, history: list, adaptation_line: str) -> dict:
        """Rodada em que o coadjuvante fala primeiro e a persona da vez fecha a rodada.

        O coadjuvante responde ao que o aluno disse ou dá o fato da função dele, sem pergunta:
        se a pergunta da rodada ficasse com ele, o aluno responderia a quem não conduz a cena,
        e a persona da vez reagiria a uma resposta dada a outro. A ausência de pergunta vem da
        instrução da fala (`line_instruction`), e a fala é dita como o modelo a gerou. A persona
        da vez continua sendo a mesma na rodada seguinte.
        """
        supporting = content.supporting_role()
        participation = scene_participation(content, supporting.key, history)
        system = build_system_prompt(
            content,
            supporting,
            memory,
            adaptation_line,
            participation,
            supporting_first_before=leader,
        )
        instruction = line_instruction(supporting, participation, supporting_first_before=leader)
        llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        _, text, _ = _generate_turn(
            llm, conversation_messages(system, history, instruction), supporting, history
        )
        _speak(supporting, text)
        record_round_event(
            "supporting_entered", speaker=supporting.key, mode="first", leader=leader.key
        )
        lines = [AIMessage(content=f"[{supporting.name}] {text}")]
        lines.append(_follow_up_line(leader, supporting, history + lines, adaptation_line))
        names = [candidate.name for candidate in content.roles]
        if addressed_persona(lines[-1].content, leader.name, names) is not None:
            record_round_event("dangling_unresolved", speaker=leader.key, reason="two_lines")
        print(f"[routing] {supporting.name} entra; {leader.name} fecha a rodada")
        record_round_event("round_end", speaker=leader.key, next_speaker=leader.key)
        return {
            "messages": lines,
            "current_speaker": leader.key,
            "hand_floor_to": "",
            "addressed_by_student": False,
            "redirect_to": "",
            "supporting_enters": "",
        }

    def node_persona(state: ScenarioState) -> dict:
        key = _fallback_key(content, state)
        role = content.role(key)

        history = list(state["messages"])
        adaptation_line = adaptation_hint(history)
        addressed = bool(state.get("addressed_by_student"))
        redirect_key = state.get("redirect_to") or ""
        redirect_role = (
            content.role(redirect_key) if redirect_key in keys and redirect_key != key else None
        )
        hand_key = state.get("hand_floor_to") or ""
        hand_role = content.role(hand_key) if hand_key in keys and hand_key != key else None
        receiver = redirect_role or hand_role
        supporting = content.supporting_role()
        entering = (state.get("supporting_enters") or "") if supporting else ""

        if state.get("turn_count", 0) >= max_turns:
            final_role = final_speaker(content, role, receiver)
            text = generate_closing_line(content, final_role, history)
            _speak(final_role, text)
            record_round_event("closing", speaker=final_role.key)
            return {
                "messages": [AIMessage(content=f"[{final_role.name}] {text}")],
                "current_speaker": final_role.key,
                "scene_resolved": True,
                "hand_floor_to": "",
                "addressed_by_student": False,
                "redirect_to": "",
                "supporting_enters": "",
            }

        if state.get("turn_count", 0) == max_turns - 2 and content.closing_hint:
            final_role = final_speaker(content, role, receiver)
            text = generate_closing_hint_line(content, final_role, history)
            if text:
                _speak(final_role, text)
                record_round_event("closing_hint", speaker=final_role.key)
                return {
                    "messages": [AIMessage(content=f"[{final_role.name}] {text}")],
                    "current_speaker": final_role.key,
                    "hand_floor_to": "",
                    "addressed_by_student": False,
                    "redirect_to": "",
                    "supporting_enters": "",
                }

        if entering == "first":
            return supporting_first_round(role, history, adaptation_line)

        participation = scene_participation(content, key, history)
        turn_marks = {
            "redirect_to": None if entering == "after" else redirect_role,
            "hand_floor_to": hand_role,
            "supporting_follows": supporting if entering == "after" else None,
        }
        system = build_system_prompt(
            content,
            role,
            memory,
            adaptation_line,
            participation,
            addressed_by_student=addressed and entering != "after",
            **turn_marks,
        )
        instruction = line_instruction(role, participation, **turn_marks)
        messages = conversation_messages(system, history, instruction)
        if entering == "after":
            receiver = None

        llm = get_structured_llm(ModelPurpose.PERSONA, PersonaTurn)
        turn, text, from_fallback = _generate_turn(llm, messages, role, history)
        directed = receiver.key if receiver else key
        if turn.pass_to in keys and turn.pass_to not in (key, directed):
            print(f"[routing] {role.name} tentou passar a vez; quem decide e o diretor de cena")
            record_round_event("handoff_ignored", speaker=key, reason="director_decides")

        _speak(role, text)
        print(f"[routing] current_speaker={key}")

        lines = [AIMessage(content=f"[{role.name}] {text}")]
        speaker = role

        def speak_after(other: Role, previous: Role) -> None:
            """Faz `other` falar na mesma rodada, depois de `previous`.

            O coadjuvante que fala depois fecha a rodada com uma pergunta curta, sem assumir a
            conversa, então recebe a instrução própria dele em vez da passagem de vez comum.
            """
            lines.append(_follow_up_line(other, previous, history + lines, adaptation_line))

        next_key = key
        if entering == "after" and supporting is not None:
            record_round_event(
                "supporting_entered", speaker=supporting.key, mode="after", leader=key
            )
            speak_after(supporting, role)
            speaker = supporting
        if receiver and not from_fallback:
            record_round_event(
                "handoff",
                origin=key,
                target=receiver.key,
                reason="student" if redirect_role else "hand_floor",
                line=text,
            )
            speak_after(receiver, role)
            speaker = receiver
            next_key = key if receiver.supporting else receiver.key
            print(f"[routing] passagem de {role.name} para {receiver.name}")

        names = [candidate.name for candidate in content.roles]
        target_name = addressed_persona(lines[-1].content, speaker.name, names)
        if target_name is not None and supporting is not None and len(lines) >= 2:
            record_round_event("dangling_unresolved", speaker=speaker.key, reason="two_lines")
            target_name = None
        if target_name is not None:
            target = next(candidate for candidate in content.roles if candidate.name == target_name)
            print(
                f"[routing] fala de {speaker.name} dirigida a {target.name}; "
                f"{target.name} responde na mesma rodada"
            )
            record_round_event("dangling_answered", speaker=speaker.key, target=target.key)
            speak_after(target, speaker)
            speaker = target
            next_key = next_key if target.supporting else target.key
            if addressed_persona(lines[-1].content, speaker.name, names) is not None:
                record_round_event("dangling_unresolved", speaker=speaker.key)

        print(f"[routing] next round current_speaker={next_key}")
        record_round_event("round_end", speaker=speaker.key, next_speaker=next_key)

        return {
            "messages": lines,
            "current_speaker": next_key,
            "hand_floor_to": "",
            "addressed_by_student": False,
            "redirect_to": "",
            "supporting_enters": "",
        }

    return node_persona
