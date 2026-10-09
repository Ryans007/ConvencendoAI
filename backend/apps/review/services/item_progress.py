from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from apps.review.services.schedule import ReviewOutcome

STEP_REPEAT_CORRECTED = 1
STEP_NEW_SENTENCE = 2
STEPS = (STEP_REPEAT_CORRECTED, STEP_NEW_SENTENCE)
MAX_ATTEMPTS = 2


class AnswerLike(Protocol):
    """O que as regras precisam saber de uma resposta: onde ela foi dada e se estava certa."""

    step: int
    attempt: int
    correct: bool


@dataclass(frozen=True)
class ItemProgress:
    """Onde a revisão de um item está: a etapa e a tentativa da próxima resposta.

    Quando `finished` é verdadeiro, a etapa 2 já terminou e `step` e `attempt` descrevem a
    última resposta dada.
    """

    step: int
    attempt: int
    finished: bool


def _step_answers(answers: Sequence[AnswerLike], step: int) -> list[AnswerLike]:
    return [answer for answer in answers if answer.step == step]


def _step_ended(step_answers: Sequence[AnswerLike]) -> bool:
    """Uma etapa termina no primeiro acerto ou na segunda tentativa, certa ou errada."""
    return any(answer.correct for answer in step_answers) or len(step_answers) >= MAX_ATTEMPTS


def item_progress(answers: Sequence[AnswerLike]) -> ItemProgress:
    """Calcula a etapa e a tentativa seguintes a partir das respostas ainda sem resultado.

    O estado nunca é guardado: derivá-lo das respostas gravadas faz o item retomado continuar
    exatamente de onde parou, e impede o cliente de pedir uma etapa ou uma tentativa que o
    servidor não deu. A etapa 2 acontece mesmo quando a etapa 1 termina sem acerto.
    """
    for step in STEPS:
        step_answers = _step_answers(answers, step)
        if not _step_ended(step_answers):
            return ItemProgress(step=step, attempt=len(step_answers) + 1, finished=False)
    return ItemProgress(
        step=STEP_NEW_SENTENCE,
        attempt=len(_step_answers(answers, STEP_NEW_SENTENCE)),
        finished=True,
    )


def item_outcome(answers: Sequence[AnswerLike]) -> ReviewOutcome:
    """O resultado de uma revisão terminada, que é o que move o item no calendário.

    Errar uma etapa nas duas tentativas é erro, mesmo que a outra tenha sido certa. Acertar
    as duas só vale como "de primeira" se nenhuma precisou da segunda tentativa.
    """
    first_try = True
    for step in STEPS:
        step_answers = _step_answers(answers, step)
        if not any(answer.correct for answer in step_answers):
            return ReviewOutcome.FAILED
        if not step_answers[0].correct:
            first_try = False
    return ReviewOutcome.FIRST_TRY if first_try else ReviewOutcome.SECOND_TRY


def revealed_correct(
    *, step: int, attempt: int, correct: bool, item_correct: str, correction: str
) -> str:
    """O que a tela pode mostrar como forma correta depois de uma resposta.

    Só ao fim de uma etapa, porque antes disso a forma correta é a própria resposta: no fim
    da etapa 1 é a forma correta do item, com ou sem acerto; no fim da etapa 2 sem acerto é a
    frase do aluno corrigida pelo professor. Num primeiro erro, ou num acerto da etapa 2, nada
    é revelado.
    """
    step_ended = correct or attempt >= MAX_ATTEMPTS
    if not step_ended:
        return ""
    if step == STEP_REPEAT_CORRECTED:
        return item_correct
    return "" if correct else correction
