from langchain_core.messages import BaseMessage, HumanMessage

ADAPT_WINDOW = 2
ADAPT_MIN_WORDS = 8

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
    """Os últimos turnos do aluno indicam que ele está com dificuldade?"""
    turns = _student_turns(messages)
    if not turns:
        return False

    recent = turns[-ADAPT_WINDOW:]
    if any(asked_for_help(t) for t in recent):
        return True

    word_counts = [len(t.split()) for t in recent]
    average = sum(word_counts) / len(word_counts)
    return average < ADAPT_MIN_WORDS


def adaptation_hint(messages: list[BaseMessage]) -> str:
    """Linha a injetar no prompt da persona, ou '' se não há ajuste a fazer.

    Deliberadamente não existe o caminho inverso (endurecer quando os turnos são
    longos): contagem de palavras não mede fluência, e subir a dificuldade é
    decisão da trilha, não desta heurística.
    """
    turns = _student_turns(messages)
    if not turns:
        return ""

    if is_struggling(messages):
        return (
            "ADAPT NOW: the student is struggling. Simplify your English, ask one "
            "very short question, and if useful offer two options for them to "
            "choose from. Be encouraging and patient."
        )
    return ""
