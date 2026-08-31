from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def transcript_text(messages: list[BaseMessage], last: int | None = None) -> str:
    """Retorna a transcrição no formato "Student: ..." / "[Nome] ...".

    `last` limita às N últimas mensagens — útil para prompts curtos.
    """
    relevant = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
    if last:
        relevant = relevant[-last:]

    lines = []
    for message in relevant:
        content = (message.content or "").strip()
        if isinstance(message, HumanMessage):
            lines.append(f"Student: {content}")
        else:
            # Já vem prefixado com "[Nome] ..." pelo nó da persona.
            lines.append(content)
    return "\n".join(lines)
