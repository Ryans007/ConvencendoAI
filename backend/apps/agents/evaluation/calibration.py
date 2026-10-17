import csv
import json
import random
import shutil
from pathlib import Path
from typing import Any

from apps.agents.evaluation.case_loader import LoadedCases
from apps.agents.evaluation.judge import CONTEXT_LINES, context_lines
from apps.agents.evaluation.schemas import ROLE_ITEMS

REVIEW_COLUMNS = [
    "id",
    "source",
    "context",
    "line",
    "item",
    "item_label",
    "judge",
    "reason",
    "human",
]
CONTEXT_SEPARATOR = " | "

_YES = {"yes", "y", "sim", "s"}
_NO = {"no", "n", "nao", "não"}


def _join_context(lines: list[str]) -> str:
    return CONTEXT_SEPARATOR.join(lines)


def judged_items(
    situations: list[dict[str, Any]], sessions: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Lista cada item julgado com sim ou não, com a fala e o contexto, para a revisão humana."""
    items = []
    for source in (*situations, *sessions):
        origin = source.get("situation") or source.get("session", "")
        for judged in source.get("roles", []):
            for item, verdict in judged.get("items", {}).items():
                if verdict["answer"] in ("yes", "no"):
                    items.append(
                        {
                            "source": origin,
                            "context": _join_context(judged.get("context", [])),
                            "line": judged["line"],
                            "item": item,
                            "item_label": ROLE_ITEMS[item][0],
                            "judge": verdict["answer"],
                            "reason": verdict["reason"],
                        }
                    )
    return items


def write_review_file(
    items: list[dict[str, str]], count: int, path: Path, rng: random.Random | None = None
) -> int:
    """Grava uma amostra aleatória dos itens julgados para a pessoa revisar; devolve o tamanho.

    A coluna `human` fica em branco: a pessoa escreve `yes` ou `no` (ou `sim` e `não`) conforme
    concorde que a fala cumpre o item, e `read_agreement` compara com a resposta do juiz. A
    coluna `context` traz as falas que vieram antes, as mesmas que o juiz recebeu.
    """
    chosen = (rng or random.Random()).sample(items, min(count, len(items)))
    rows = [{"id": number, **item, "human": ""} for number, item in enumerate(chosen, 1)]
    _write_rows(path, rows)
    return len(chosen)


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    """Lê o arquivo de revisão tolerando o alinhamento que editores de CSV acrescentam.

    Alguns editores alinham as colunas com espaços (`id, source      , line   , item`) e gravam o
    texto entre aspas depois de um espaço (`, "texto, com vírgula"`). O leitor padrão só reconhece
    a aspa de abertura no começo do campo, então partiria o texto nas vírgulas internas e
    deslocaria as colunas. `skipinitialspace` resolve isso, e os espaços que sobram ao redor de
    cabeçalhos e valores são removidos.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle, skipinitialspace=True)
        try:
            header = [name.strip() for name in next(reader)]
        except StopIteration:
            return []
        return [
            {name: (value or "").strip() for name, value in zip(header, row)}
            for row in reader
            if any(cell.strip() for cell in row)
        ]


def _normalise(value: str) -> str | None:
    cleaned = value.strip().lower()
    if cleaned in _YES:
        return "yes"
    if cleaned in _NO:
        return "no"
    return None


def read_agreement(path: Path) -> dict[str, Any]:
    """Calcula a concordância entre o juiz e a pessoa no arquivo revisado.

    Só entram as linhas em que a pessoa respondeu; as em branco e as com resposta que não é
    sim nem não ficam fora, e são contadas à parte. Devolve o total, a concordância por item e as
    discordâncias, com a fala e o motivo do juiz.
    """
    reviewed = skipped = 0
    agreed = 0
    by_item: dict[str, list[int]] = {}
    disagreements = []
    for row in read_rows(path):
        human = _normalise(row.get("human", ""))
        judge = _normalise(row.get("judge", ""))
        if human is None or judge is None:
            skipped += 1
            continue
        reviewed += 1
        same = human == judge
        agreed += 1 if same else 0
        counts = by_item.setdefault(row["item"], [0, 0])
        counts[0] += 1 if same else 0
        counts[1] += 1
        if not same:
            disagreements.append(row)
    return {
        "reviewed": reviewed,
        "skipped": skipped,
        "agreement": agreed / reviewed if reviewed else None,
        "by_item": {item: (counts[0], counts[1]) for item, counts in by_item.items()},
        "disagreements": disagreements,
    }


def _context_index(results: dict[str, Any], cases: LoadedCases) -> dict[tuple[str, str], str]:
    """Para cada (origem, fala) julgada, o contexto que o juiz recebeu.

    Usa o contexto guardado quando existe. Nos resultados antigos, que não o guardavam, reconstrói:
    nas sessões, pelas falas anteriores da transcrição; nas situações, pelo histórico do caso
    seguido das falas anteriores da mesma rodada.
    """
    index: dict[tuple[str, str], str] = {}
    situation_history = {
        situation.id: context_lines(situation.history, limit=None) for situation in cases.situations
    }
    for sample in results.get("situations", []):
        lines = situation_history.get(sample["situation"], [])
        round_lines = sample.get("round", [])
        for judged in sample.get("roles", []):
            if "context" in judged:
                context = judged["context"]
            else:
                line = judged["line"]
                before = round_lines[: round_lines.index(line)] if line in round_lines else []
                context = [*lines, *before][-CONTEXT_LINES:]
            index.setdefault((sample["situation"], judged["line"]), _join_context(context))
    for session in results.get("sessions", []):
        transcript = session.get("transcript", [])
        for judged in session.get("roles", []):
            if "context" in judged:
                context = judged["context"]
            else:
                position = transcript.index(judged["line"]) if judged["line"] in transcript else 0
                context = transcript[max(0, position - CONTEXT_LINES) : position]
            index.setdefault((session["session"], judged["line"]), _join_context(context))
    return index


def add_context(review_path: Path, results_path: Path, cases: LoadedCases) -> dict[str, int]:
    """Acrescenta a coluna de contexto a um arquivo de revisão já preenchido, sem perder respostas.

    Guarda uma cópia do arquivo original ao lado (`.bak`), lê o arquivo com a leitura tolerante,
    procura o contexto de cada linha pelos resultados da mesma execução e regrava o arquivo com as
    colunas padrão. As respostas da coluna `human` são mantidas como estão. Devolve quantas linhas
    ganharam contexto e quantas não foram encontradas nos resultados.
    """
    results = json.loads(results_path.read_text(encoding="utf-8"))
    index = _context_index(results, cases)
    rows = read_rows(review_path)
    shutil.copy2(review_path, review_path.with_suffix(review_path.suffix + ".bak"))
    found = missing = 0
    for row in rows:
        context = index.get((row.get("source", ""), row.get("line", "")))
        if context is None:
            missing += 1
            context = row.get("context", "")
        else:
            found += 1
        row["context"] = context
    _write_rows(review_path, rows)
    return {"found": found, "missing": missing}
