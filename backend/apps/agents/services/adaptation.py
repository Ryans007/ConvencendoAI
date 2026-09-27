from langchain_core.messages import BaseMessage, HumanMessage

ADAPT_WINDOW = 2

_HELP_MARKERS = (
    "how do i say", "how do you say", "how to say",
    "what's the word", "what is the word", "the word for",
    "can you repeat", "could you repeat", "repeat that", "say that again",
    "more slowly", "slower please", "speak slowly",
    "i don't understand", "i didn't understand", "i don't know how to say",
)


def _student_turns(messages: list[BaseMessage]) -> list[str]:
    return [(m.content or "").strip() for m in messages if isinstance(m, HumanMessage)]


def asked_for_help(text: str) -> bool:
    """O aluno pediu ajuda explicitamente no turno atual?"""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _HELP_MARKERS)


def is_struggling(messages: list[BaseMessage]) -> bool:
    """O aluno pediu ajuda explicitamente num dos últimos turnos?

    Só o pedido explícito conta. Resposta curta não é sinal de dificuldade: no nível de
    compreensão, responder "Yes, I did." é exatamente o esperado, e tratar isso como
    dificuldade fazia a persona repetir a mesma pergunta a cada rodada.
    """
    turns = _student_turns(messages)
    return any(asked_for_help(turn) for turn in turns[-ADAPT_WINDOW:])


def adaptation_hint(messages: list[BaseMessage]) -> str:
    """Linha a injetar no prompt da persona, ou '' se não há ajuste a fazer."""
    if is_struggling(messages):
        return (
            "ADAPT NOW: the student is struggling. Simplify your English, ask one "
            "very short question, and if useful offer two options for them to "
            "choose from. Be encouraging and patient."
        )
    return ""
