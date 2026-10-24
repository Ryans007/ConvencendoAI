from dataclasses import dataclass

from apps.progress.services.speech_metrics import SessionSpeechMetrics
from apps.progress.speech_bands import (
    DIVERSITY_BAND,
    MEASURED_FLUENCY_SHARE,
    RANGE_BAND,
    LevelSpeechRules,
)


@dataclass(frozen=True)
class MeasuredPart:
    """Uma medida que entrou numa nota, com a fração que ela valeu e o peso dela na medida."""

    fraction: float
    share: float


def measured_fluency(
    metrics: SessionSpeechMetrics | None, rules: LevelSpeechRules
) -> float | None:
    """A fluência medida, de 0 a 1, ou vazia quando a sessão não tem tempo de reação.

    Sem reação não há fluência medida: a reação é a medida que todos os níveis usam. Uma medida
    que o nível usa, mas que a sessão não tem, sai da conta, e as que sobram são reponderadas
    entre si, para a falta de um dado não virar zero.
    """
    if metrics is None or metrics.reaction_seconds is None:
        return None
    fluency = rules.fluency
    parts = [
        MeasuredPart(fluency.reaction.fraction(metrics.reaction_seconds), fluency.reaction_share)
    ]
    if fluency.speed is not None and metrics.words_per_minute is not None:
        speed = fluency.speed.fraction(metrics.words_per_minute)
        parts.append(MeasuredPart(speed, fluency.speed_share))
    if fluency.pauses is not None and metrics.long_pauses_per_100_words is not None:
        pauses = fluency.pauses.fraction(metrics.long_pauses_per_100_words)
        parts.append(MeasuredPart(pauses, fluency.pauses_share))
    return _weighted_average(parts)


def fluency_score(
    weight: int, judged_value: int, metrics: SessionSpeechMetrics | None, rules: LevelSpeechRules
) -> int:
    """A nota de fluência: 70% a fluência medida e 30% o julgamento da IA, limitada ao peso.

    A parte da IA continua porque o número não vê se a frase saiu entendível nem se o aluno se
    corrigiu no meio: sem ela, quem fala rápido e embolado tiraria a nota máxima. Sem fluência
    medida, a nota é o julgamento da IA, como na execução por texto.
    """
    measured = measured_fluency(metrics, rules)
    if measured is None or weight <= 0:
        return _clamp(judged_value, weight)
    judged = judged_value / weight
    blended = MEASURED_FLUENCY_SHARE * measured + (1 - MEASURED_FLUENCY_SHARE) * judged
    return _clamp(weight * blended, weight)


def vocabulary_score(
    weight: int, judged_value: int, metrics: SessionSpeechMetrics | None, rules: LevelSpeechRules
) -> int:
    """A nota de vocabulário: a precisão julgada pela IA, combinada com diversidade e alcance
    nas proporções do nível, limitada ao peso.

    Sem diversidade calculada (sessão por texto ou com poucas palavras), a nota é o julgamento
    da IA. A precisão — se a palavra era a certa para o contexto — fica sempre com a IA, porque
    nenhuma fórmula a mede.
    """
    if metrics is None or metrics.lexical_diversity is None or weight <= 0:
        return _clamp(judged_value, weight)
    vocabulary = rules.vocabulary
    parts = [
        MeasuredPart(judged_value / weight, vocabulary.judged_share),
        MeasuredPart(
            DIVERSITY_BAND.fraction(metrics.lexical_diversity), vocabulary.diversity_share
        ),
    ]
    if metrics.lexical_range is not None:
        lexical_range = RANGE_BAND.fraction(metrics.lexical_range)
        parts.append(MeasuredPart(lexical_range, vocabulary.range_share))
    return _clamp(weight * _weighted_average(parts), weight)


def _weighted_average(parts: list[MeasuredPart]) -> float:
    """A média das frações pelos pesos de cada uma, reponderada sobre as que entraram."""
    total_share = sum(part.share for part in parts)
    if total_share <= 0:
        return parts[0].fraction
    return sum(part.fraction * part.share for part in parts) / total_share


def _clamp(value: float, weight: int) -> int:
    """A nota arredondada e limitada entre 0 e o peso, para nunca confiar numa conta que passe."""
    return int(max(0, min(weight, round(value))))
