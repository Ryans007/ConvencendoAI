import logging

from apps.llm.models import AgentModelConfig
from apps.review.models import ReviewAnswer, ReviewOccurrence
from apps.review.services.answering import AnswerFailed
from apps.usage.services.owner import usage_owner
from apps.voice.services.failures import classify_failure
from apps.voice.services.tts import synthesize

logger = logging.getLogger(__name__)


def correct_form_audio(answer: ReviewAnswer) -> bytes:
    """Sintetiza a forma correta que a tela revelou depois desta resposta.

    O texto vem sempre da própria resposta, nunca do pedido, e só existe quando a etapa
    terminou: assim o áudio não consegue adiantar uma resposta, e ninguém usa o endpoint
    para sintetizar um texto qualquer às custas do sistema. A voz é a da configuração única
    de modelos, a mesma para todos os alunos. Uma falha do provedor levanta `AnswerFailed`
    com o código que o cliente já sabe tratar.
    """
    voice = AgentModelConfig.get_solo().review_voice
    try:
        with usage_owner(user=answer.item.user, review_item=answer.item):
            return synthesize(answer.revealed_correct, voice)
    except Exception as exc:
        logger.exception("falha ao sintetizar a forma correta da revisão")
        raise AnswerFailed(classify_failure(exc)) from exc


def occurrence_correct_audio(occurrence: ReviewOccurrence) -> bytes:
    """Sintetiza a forma correta de um erro do relatório da sessão, na voz do "Ouvir".

    O texto vem da ocorrência gravada, nunca do pedido, pelo mesmo motivo da revisão: o
    endpoint não sintetiza texto livre. O uso fica ligado ao item de revisão, para entrar no
    mesmo limite por minuto do "Ouvir" da revisão.
    """
    voice = AgentModelConfig.get_solo().review_voice
    try:
        with usage_owner(
            user=occurrence.item.user, attempt=occurrence.attempt, review_item=occurrence.item
        ):
            return synthesize(occurrence.correct, voice)
    except Exception as exc:
        logger.exception("falha ao sintetizar a forma correta do relatório")
        raise AnswerFailed(classify_failure(exc)) from exc
