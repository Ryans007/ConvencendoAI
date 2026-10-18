import re

_SPEAKER = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)


def speaker_and_text(line: str) -> tuple[str, str] | None:
    """Separa a fala de persona "[Nome] texto" no nome e no texto; `None` para outra linha."""
    match = _SPEAKER.match(line)
    return (match.group(1), match.group(2)) if match else None


def addressed_persona(line: str, speaker_name: str, names: list[str]) -> str | None:
    """O nome da outra persona a quem a fala se dirige, pelo vocativo logo no começo, ou `None`.

    Considera só o vocativo nas primeiras palavras ("Tom, this one is yours." ou "Good
    question. Rachel, can you answer?"), que é como uma persona passa a vez. É uma heurística:
    o sistema usa a mesma regra para garantir que a rodada termine para o aluno e a avaliação
    para medir quantas rodadas terminaram assim.
    """
    parsed = speaker_and_text(line)
    text = parsed[1] if parsed else line
    for name in names:
        if name == speaker_name:
            continue
        if re.match(rf"^\W*(?:\w+[,.!]?\s+){{0,2}}{re.escape(name)}\s*[,?]", text):
            return name
    return None


def is_addressed_to_another(line: str, speaker_name: str, names: list[str]) -> bool:
    """A fala se dirige a outra persona, pelo nome, logo no começo."""
    return addressed_persona(line, speaker_name, names) is not None
