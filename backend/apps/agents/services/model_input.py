from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from apps.agents.services.transcript import transcript_text

_NO_ONE_SPOKE_YET = "(no one has spoken yet)"


def conversation_messages(system_prompt: str, history: list[BaseMessage]) -> list[BaseMessage]:
    """Monta o que a persona e o roteador recebem: as instruções e a conversa como texto.

    A conversa vai numa única mensagem, com cada fala identificada pelo autor. Enviá-la
    como turnos, com as falas de todas as personas como mensagens do "assistente", faz o
    modelo tratá-las como falas que ele mesmo já disse: em vez de seguir a instrução, ele
    continua o padrão do histórico — escreve falas no formato `[Nome] ...` no lugar do
    schema, repete perguntas e respostas. Medido com o mesmo modelo, a conversa como texto
    único eliminou as recusas do provedor e as repetições. O avaliador e as falas de
    fechamento já enviam a conversa assim.
    """
    transcript = transcript_text(history) or _NO_ONE_SPOKE_YET
    body = (
        f"CONVERSATION SO FAR\n{transcript}\n\n"
        "Now respond, following your instructions."
    )
    return [SystemMessage(content=system_prompt), HumanMessage(content=body)]
