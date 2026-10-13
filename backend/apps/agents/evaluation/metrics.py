import re
from collections import Counter
from typing import Any

from apps.agents.services.scenario_content import ScenarioContent

_SPEAKER = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)


def speaker_and_text(line: str) -> tuple[str, str] | None:
    """Separa a fala de persona "[Nome] texto" no nome e no texto; `None` para outra linha."""
    match = _SPEAKER.match(line)
    return (match.group(1), match.group(2)) if match else None


def split_rounds(transcript: list[str]) -> list[list[str]]:
    """Agrupa as falas de persona por rodada: a abertura e uma após cada fala do aluno."""
    rounds: list[list[str]] = [[]]
    for line in transcript:
        if line.startswith("Student:"):
            rounds.append([])
        else:
            rounds[-1].append(line)
    return rounds


def question_count(lines: list[str]) -> int:
    """Quantos pontos de interrogação há nas falas: cada um conta como uma pergunta ao aluno."""
    return sum(line.count("?") for line in lines)


def is_addressed_to_another(line: str, speaker_name: str, names: list[str]) -> bool:
    """A fala se dirige a outra persona, pelo nome, logo no começo.

    Considera só o vocativo nas primeiras palavras ("Tom, this one is yours." ou "Good
    question. Rachel, can you answer?"), que é como uma persona passa a vez. É uma heurística:
    o relatório lista as falas apontadas para a pessoa conferir.
    """
    parsed = speaker_and_text(line)
    text = parsed[1] if parsed else line
    for name in names:
        if name == speaker_name:
            continue
        if re.match(rf"^\W*(?:\w+[,.!]?\s+){{0,2}}{re.escape(name)}\s*[,?]", text):
            return True
    return False


def introduces_self(line: str, name: str) -> bool:
    """A fala se apresenta: "I'm Tom", "I am Tom", "my name is Tom" ou "this is Tom"."""
    return bool(re.search(rf"\b(I'm|I am|my name is|this is)\s+{re.escape(name)}\b", line, re.I))


def round_stats(rounds: list[list[str]], names: list[str]) -> list[dict[str, Any]]:
    """Por rodada com fala de persona: quem a fechou, as perguntas e se ficou dirigida a outra."""
    stats = []
    for lines in rounds:
        if not lines:
            continue
        last = speaker_and_text(lines[-1])
        speaker = last[0] if last else ""
        stats.append(
            {
                "leader": speaker,
                "questions": question_count(lines),
                "dangling": is_addressed_to_another(lines[-1], speaker, names),
                "last_line": lines[-1],
            }
        )
    return stats


def _runs(leaders: list[str]) -> list[int]:
    runs: list[int] = []
    for index, leader in enumerate(leaders):
        if index and leader == leaders[index - 1]:
            runs[-1] += 1
        else:
            runs.append(1)
    return runs


def change_causes(events: list[dict[str, Any]]) -> Counter:
    """Conta por que a condução da conversa mudou, a partir dos eventos registrados nos nós."""
    causes: Counter = Counter()
    for event in events:
        kind = event["kind"]
        if kind == "addressed":
            same = event["speaker"] == event["previous"]
            causes["student_same" if same else "student_directed"] += 1
        elif kind in ("balance_takeover", "handoff", "handoff_ignored"):
            causes[kind] += 1
    return causes


def session_metrics(
    transcript: list[str], events: list[dict[str, Any]], content: ScenarioContent
) -> dict[str, Any]:
    """Calcula as métricas de troca de uma sessão a partir da transcrição e dos eventos."""
    names = [role.name for role in content.roles]
    key_by_name = {role.name: role.key for role in content.roles}
    stats = round_stats(split_rounds(transcript), names)
    leaders = [item["leader"] for item in stats]
    runs = _runs(leaders)

    first_lines: dict[str, str] = {}
    for line in transcript:
        parsed = speaker_and_text(line)
        if parsed:
            first_lines.setdefault(parsed[0], parsed[1])
    opener = content.roles[0].name
    newcomers = [name for name in names if name != opener and name in first_lines]
    intros = {
        name: introduces_self(first_lines[name], name) for name in names if name in first_lines
    }

    return {
        "rounds": len(stats),
        "lines_by_persona": dict(
            Counter(
                key_by_name.get(parsed[0], parsed[0])
                for parsed in (speaker_and_text(line) for line in transcript)
                if parsed
            )
        ),
        "leaders": [key_by_name.get(leader, leader) for leader in leaders],
        "changes": sum(1 for a, b in zip(leaders, leaders[1:]) if a != b),
        "causes": dict(change_causes(events)),
        "max_run": max(runs) if runs else 0,
        "over_limit_runs": sum(1 for run in runs if run > content.max_consecutive_turns),
        "multi_question_rounds": sum(1 for item in stats if item["questions"] > 1),
        "dangling_rounds": [item["last_line"] for item in stats if item["dangling"]],
        "introduced": intros,
        "newcomers": len(newcomers),
        "newcomers_introduced": sum(1 for name in newcomers if intros[name]),
    }
