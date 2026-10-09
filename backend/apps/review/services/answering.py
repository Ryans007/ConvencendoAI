import logging
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from django.db import transaction

from apps.agents.services.review_teacher import ReviewJudgmentFailed, judge_review_answer
from apps.agents.services.schemas import ReviewVerdict
from apps.review.models import (
    ReviewAnswer,
    ReviewItem,
    ReviewOccurrence,
    ReviewResult,
    ReviewResultKind,
)
from apps.review.services.item_progress import (
    ItemProgress,
    item_outcome,
    item_progress,
    revealed_correct,
)
from apps.review.services.schedule import due_date, is_mastered, next_box
from apps.voice.services.failures import SessionErrorCode, classify_failure
from apps.voice.services.stt import transcribe

logger = logging.getLogger(__name__)


class AnswerStatus(StrEnum):
    """Se a fala foi julgada ou se nada foi ouvido nela."""

    JUDGED = "judged"
    NOT_HEARD = "not_heard"


class AnswerFailed(Exception):
    """A transcrição ou o julgamento falharam; nada foi gravado e o aluno pode reenviar."""

    def __init__(self, code: SessionErrorCode):
        super().__init__(code.value)
        self.code = code


class ProgressChanged(Exception):
    """O item andou entre o início e a gravação da resposta, por exemplo num envio duplicado."""


@dataclass(frozen=True)
class AnsweredItem:
    """O que o envio de uma resposta produziu, para a view montar a resposta da API.

    `next_progress` é a próxima etapa e tentativa, e fica vazio quando a revisão do item
    terminou, caso em que `result` traz o que ela fez com o calendário.
    """

    status: AnswerStatus
    answer: ReviewAnswer | None = None
    next_progress: ItemProgress | None = None
    result: ReviewResult | None = None

    @property
    def mastered(self) -> bool:
        return self.result is not None and is_mastered(self.result.box_after)


def _open_answers(item: ReviewItem) -> list[ReviewAnswer]:
    return list(item.answers.filter(result__isnull=True).order_by("created_at", "id"))


def _transcribe(audio: bytes) -> str:
    try:
        return transcribe(audio)
    except Exception as exc:
        logger.exception("falha ao transcrever a resposta da revisão")
        raise AnswerFailed(classify_failure(exc)) from exc


def _judge(
    item: ReviewItem, occurrence: ReviewOccurrence, progress: ItemProgress, heard: str
) -> ReviewVerdict:
    try:
        return judge_review_answer(
            rule=item.rule,
            said=occurrence.produced,
            correct=occurrence.correct,
            step=progress.step,
            attempt=progress.attempt,
            heard=heard,
        )
    except ReviewJudgmentFailed as exc:
        logger.exception("o professor da revisão não devolveu um veredito")
        raise AnswerFailed(SessionErrorCode.PROVIDER_UNAVAILABLE) from exc
    except Exception as exc:
        logger.exception("falha ao julgar a resposta da revisão")
        raise AnswerFailed(classify_failure(exc)) from exc


def _finish_review(item: ReviewItem, answers: list[ReviewAnswer], today: date) -> ReviewResult:
    """Grava o resultado da revisão e move o item no calendário a partir de hoje."""
    outcome = item_outcome(answers)
    box_before = item.box
    item.box = next_box(box_before, outcome)
    item.due_on = due_date(item.box, today)
    item.save(update_fields=["box", "due_on", "updated_at"])
    result = ReviewResult.objects.create(
        item=item,
        outcome=ReviewResultKind(outcome.value),
        box_before=box_before,
        box_after=item.box,
        due_on_after=item.due_on,
    )
    item.answers.filter(result__isnull=True).update(result=result)
    return result


def answer_item(item: ReviewItem, audio: bytes, today: date) -> AnsweredItem:
    """Transcreve e julga uma resposta falada do aluno, e grava o que ela produziu.

    A etapa e a tentativa saem das respostas já gravadas, nunca do pedido. A transcrição e o
    julgamento levam segundos e ficam fora de qualquer transação; só depois o item é travado
    e o progresso conferido de novo, para um envio duplicado, que terminaria a mesma
    tentativa duas vezes, ser recusado com `ProgressChanged` em vez de gravar em dobro. Uma
    fala sem texto devolve `NOT_HEARD` e nada é gravado, e uma falha do provedor levanta
    `AnswerFailed` também sem gravar, então nenhuma das duas gasta a tentativa. Ao fim da
    etapa 2 o resultado é gravado na mesma transação da resposta, e a revisão do item
    termina ali, sem esperar o fim da rodada.
    """
    progress = item_progress(_open_answers(item))
    if progress.finished:
        raise ProgressChanged(item.pk)

    heard = _transcribe(audio).strip()
    if not heard:
        return AnsweredItem(status=AnswerStatus.NOT_HEARD)

    occurrence = item.occurrences.first()
    verdict = _judge(item, occurrence, progress, heard)

    with transaction.atomic():
        locked = ReviewItem.objects.select_for_update().get(pk=item.pk)
        answers = _open_answers(locked)
        if locked.archived_at is not None or item_progress(answers) != progress:
            raise ProgressChanged(item.pk)

        answer = ReviewAnswer.objects.create(
            item=locked,
            step=progress.step,
            attempt=progress.attempt,
            heard=heard,
            correct=verdict.correct,
            feedback=verdict.feedback,
            correction=verdict.correction,
            revealed_correct=revealed_correct(
                step=progress.step,
                attempt=progress.attempt,
                correct=verdict.correct,
                item_correct=occurrence.correct,
                correction=verdict.correction,
            ),
        )
        answers.append(answer)
        next_progress = item_progress(answers)
        if not next_progress.finished:
            return AnsweredItem(
                status=AnswerStatus.JUDGED, answer=answer, next_progress=next_progress
            )
        result = _finish_review(locked, answers, today)
        return AnsweredItem(status=AnswerStatus.JUDGED, answer=answer, result=result)
