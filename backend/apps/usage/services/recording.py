import logging
from decimal import Decimal

from django.db import transaction

from apps.usage.constants import UsagePurpose
from apps.usage.models import ModelUsage
from apps.usage.services.cost import Cost, chat_cost, speech_cost, transcription_cost
from apps.usage.services.owner import current_owner

logger = logging.getLogger(__name__)

_COST_PLACES = Decimal("0.00000001")


def _save(
    *, llm_model, purpose: str, cost: Cost, duration_ms: int, failed: bool, error_code: str,
    **measures,
) -> None:
    """Grava a linha de uso com o dono atual; qualquer erro vai só para o log.

    A gravação do uso nunca pode derrubar a sessão nem a revisão do aluno, e roda num
    savepoint próprio para que uma falha dela não deixe a transação do chamador inutilizável.
    """
    owner = current_owner()
    try:
        with transaction.atomic():
            ModelUsage.objects.create(
                user_id=owner.user_id if owner else None,
                username_at_time=owner.username if owner else "",
                attempt_id=owner.attempt_id if owner else None,
                review_item_id=owner.review_item_id if owner else None,
                purpose=purpose,
                llm_model=llm_model,
                model_id_at_time=llm_model.model_id,
                duration_ms=duration_ms,
                failed=failed,
                error_code=error_code,
                cost_usd=cost.usd.quantize(_COST_PLACES),
                priced=cost.priced,
                **measures,
            )
    except Exception:
        logger.exception("falha ao gravar o uso do modelo")


def record_chat_call(
    *,
    llm_model,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    model_calls: int,
    duration_ms: int,
    failed: bool = False,
    error_code: str = "",
) -> None:
    """Grava o uso de uma chamada de chat: os tokens somados de todas as respostas.

    Uma chamada que falhou grava a linha sem consumo e sem custo: o que o provedor chegou a
    gerar antes de falhar não foi entregue ao aluno nem se sabe se foi cobrado.
    """
    if failed:
        input_tokens = output_tokens = model_calls = 0
    cost = Cost(Decimal(0), False) if failed else chat_cost(llm_model, input_tokens, output_tokens)
    _save(
        llm_model=llm_model,
        purpose=UsagePurpose(purpose),
        cost=cost,
        duration_ms=duration_ms,
        failed=failed,
        error_code=error_code,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_calls=model_calls,
    )


def record_transcription_call(
    *,
    llm_model,
    audio_seconds: float | None,
    duration_ms: int,
    failed: bool = False,
    error_code: str = "",
) -> None:
    """Grava o uso de uma transcrição: a duração do áudio e os segundos cobrados."""
    if failed:
        cost, billed = Cost(Decimal(0), False), None
    else:
        cost, billed = transcription_cost(llm_model, audio_seconds)
    _save(
        llm_model=llm_model,
        purpose=UsagePurpose.TRANSCRIPTION,
        cost=cost,
        duration_ms=duration_ms,
        failed=failed,
        error_code=error_code,
        audio_seconds=None if failed else audio_seconds,
        billed_audio_seconds=billed,
        model_calls=0 if failed else 1,
    )


def record_speech_call(
    *,
    llm_model,
    characters: int,
    duration_ms: int,
    failed: bool = False,
    error_code: str = "",
) -> None:
    """Grava o uso de uma síntese de voz: os caracteres do texto enviado."""
    cost = Cost(Decimal(0), False) if failed else speech_cost(llm_model, characters)
    _save(
        llm_model=llm_model,
        purpose=UsagePurpose.SPEECH,
        cost=cost,
        duration_ms=duration_ms,
        failed=failed,
        error_code=error_code,
        characters=0 if failed else characters,
        model_calls=0 if failed else 1,
    )
