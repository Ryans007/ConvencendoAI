from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from apps.agents.services.transcript import transcript_text

_NO_ONE_SPOKE_YET = "(no one has spoken yet)"


def conversation_messages(
    system_prompt: str, history: list[BaseMessage], line_instruction: str = ""
) -> list[BaseMessage]:
    """Monta o que a persona e o roteador recebem: as instruções e a conversa como texto.

    A conversa vai numa única mensagem, com cada fala identificada pelo autor. Enviá-la
    como turnos, com as falas de todas as personas como mensagens do "assistente", faz o
    modelo tratá-las como falas que ele mesmo já disse: em vez de seguir a instrução, ele
    continua o padrão do histórico — escreve falas no formato `[Nome] ...` no lugar do
    schema, repete perguntas e respostas. Medido com o mesmo modelo, a conversa como texto
    único eliminou as recusas do provedor e as repetições. O avaliador e as falas de
    fechamento já enviam a conversa assim.

    `line_instruction` é o que esta fala tem de fazer na rodada (passar a vez, recebê-la,
    falar antes do coadjuvante) e vai depois da conversa, por ser a última coisa que o modelo
    lê. Medido com o modelo real em rodadas que falhavam, o mesmo texto no fim do system
    prompt ainda deixou 1 pergunta em 60 falas de passagem e 1 estreia sem apresentação em
    48; depois da conversa, nenhuma das duas. Sem instrução, a mensagem é a de sempre.
    """
    transcript = transcript_text(history) or _NO_ONE_SPOKE_YET
    body = (
        f"CONVERSATION SO FAR\n{transcript}\n\n"
        "Now respond, following your instructions."
    )
    if line_instruction:
        body = f"{body}\n{line_instruction.strip()}"
    return [SystemMessage(content=system_prompt), HumanMessage(content=body)]
