from collections.abc import Sequence

from apps.progress.models import Attempt, SpeechTurn
from apps.progress.services.speech_metrics import TimedWord, measure_turn
from apps.progress.speech_bands import MAX_WAIT_MS


def valid_wait_ms(raw: object) -> int | None:
    """A espera informada pelo navegador, ou vazia quando ela não serve como medida.

    O valor vem do cliente, então só vale um número entre 0 e 10 minutos: ausente, negativo,
    absurdo ou de outro tipo vira espera desconhecida, e a vez fica fora da medida de reação
    sem atrapalhar a conversa.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if raw < 0 or raw > MAX_WAIT_MS:
        return None
    return int(round(raw))


def record_speech_turn(
    attempt: Attempt,
    *,
    text: str,
    words: Sequence[TimedWord],
    waited_ms: int | None,
    after_hint: bool,
) -> SpeechTurn | None:
    """Grava uma vez de fala do aluno com as medidas tiradas dos horários das palavras.

    Sem palavras com horário não há medida, e a vez não é gravada: ela não teria nada a somar à
    fluência nem ao vocabulário. A ordem é a próxima depois das vezes já gravadas da tentativa.
    """
    measure = measure_turn(words)
    if measure is None:
        return None
    order = attempt.speech_turns.count() + 1
    return SpeechTurn.objects.create(
        attempt=attempt,
        order=order,
        waited_ms=waited_ms,
        leading_silence_ms=measure.leading_silence_ms,
        speech_ms=measure.speech_ms,
        word_count=measure.word_count,
        long_pauses=measure.long_pauses,
        after_hint=after_hint,
        text=text,
    )
