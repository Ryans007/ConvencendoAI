from datetime import date, timedelta
from enum import StrEnum

BOX_INTERVAL_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30, 60, 120)
FIRST_BOX = 0
MASTERED_FROM_BOX = BOX_INTERVAL_DAYS.index(60)
LAST_BOX = len(BOX_INTERVAL_DAYS) - 1


class ReviewOutcome(StrEnum):
    """Como o aluno se saiu numa revisão de um item."""

    FIRST_TRY = "first_try"
    SECOND_TRY = "second_try"
    FAILED = "failed"


def next_box(box: int, outcome: ReviewOutcome) -> int:
    """A caixa do item depois de uma revisão.

    Caixas fixas, e não um algoritmo adaptativo: o volume é pequeno (até 4 erros por
    sessão), e um intervalo previsível é mais fácil de explicar ao aluno e de auditar.
    Acertar de primeira sobe uma caixa, sem passar da última; acertar na segunda tentativa
    repete a caixa, porque o aluno ainda hesitou; errar volta para a primeira, inclusive
    num item dominado. Trocar de algoritmo no futuro é trocar este módulo.
    """
    current = min(max(box, FIRST_BOX), LAST_BOX)
    if outcome is ReviewOutcome.FIRST_TRY:
        return min(current + 1, LAST_BOX)
    if outcome is ReviewOutcome.SECOND_TRY:
        return current
    return FIRST_BOX


def due_date(box: int, today: date) -> date:
    """O dia em que um item nesta caixa volta, a partir de hoje."""
    return today + timedelta(days=BOX_INTERVAL_DAYS[min(max(box, FIRST_BOX), LAST_BOX)])


def is_mastered(box: int) -> bool:
    """O item está dominado: o aluno já acertou de primeira na caixa de 30 dias.

    Como no Anki, o item dominado não sai da revisão: continua voltando em 60 e 120 dias,
    porque esquecer é o padrão e um reforço espaçado custa pouco.
    """
    return box >= MASTERED_FROM_BOX


def restart(today: date) -> tuple[int, date]:
    """Caixa e vencimento de um item novo, ou de um item cuja regra o aluno errou de novo."""
    return FIRST_BOX, due_date(FIRST_BOX, today)
