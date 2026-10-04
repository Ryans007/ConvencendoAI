from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

AFTER_HINT_KEY = "after_hint"
_AFTER_HINT_LABEL = "Student (after a suggested answer)"


def answered_after_hint(message: BaseMessage) -> bool:
    """A fala do aluno foi dada depois de ele ver uma dica naquela vez?"""
    return isinstance(message, HumanMessage) and bool(
        message.additional_kwargs.get(AFTER_HINT_KEY)
    )


def transcript_text(
    messages: list[BaseMessage], last: int | None = None, mark_hints: bool = False
) -> str:
    """Retorna a transcrição no formato "Student: ..." / "[Nome] ...".

    `last` limita às N últimas mensagens — útil para prompts curtos. As falas das personas
    já vêm prefixadas com "[Nome] ..." pelo nó da persona.

    Com `mark_hints`, a fala que o aluno deu depois de ver uma dica sai marcada. Só o
    avaliador liga isso, para pesar a autonomia: a persona e o roteador recebem a conversa
    sem a marca, e não sabem que o aluno pediu ajuda.
    """
    relevant = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
    if last:
        relevant = relevant[-last:]

    lines = []
    for message in relevant:
        content = (message.content or "").strip()
        if isinstance(message, HumanMessage):
            label = _AFTER_HINT_LABEL if mark_hints and answered_after_hint(message) else "Student"
            lines.append(f"{label}: {content}")
        else:
            lines.append(content)
    return "\n".join(lines)
