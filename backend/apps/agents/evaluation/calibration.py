import csv
import random
from pathlib import Path
from typing import Any

from apps.agents.evaluation.schemas import ROLE_ITEMS

REVIEW_COLUMNS = ["id", "source", "line", "item", "item_label", "judge", "reason", "human"]

_YES = {"yes", "y", "sim", "s"}
_NO = {"no", "n", "nao", "não"}


def judged_items(
    situations: list[dict[str, Any]], sessions: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Lista cada item julgado com sim ou não, com a fala, para a revisão humana."""
    items = []
    for source in (*situations, *sessions):
        origin = source.get("situation") or source.get("session", "")
        for judged in source.get("roles", []):
            for item, verdict in judged.get("items", {}).items():
                if verdict["answer"] in ("yes", "no"):
                    items.append(
                        {
                            "source": origin,
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
    concorde que a fala cumpre o item, e `read_agreement` compara com a resposta do juiz.
    """
    chosen = (rng or random.Random()).sample(items, min(count, len(items)))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for number, item in enumerate(chosen, start=1):
            writer.writerow({"id": number, **item, "human": ""})
    return len(chosen)


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
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
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
