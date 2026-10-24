from dataclasses import dataclass

from apps.catalog.models import ScenarioRole
from apps.progress.constants import PASSING_SCORE
from apps.progress.models import Attempt
from apps.progress.services.speech_metrics import SessionSpeechMetrics, session_metrics
from apps.progress.speech_bands import MEASURED_FLUENCY_SHARE, LevelSpeechRules, rules_for_level
from apps.review.models import ReviewOccurrence
from apps.review.services.queries import attempt_mistakes


@dataclass(frozen=True)
class FluencyShares:
    """Quanto cada parte pesou na fluência de uma tentativa com fluência medida."""

    measured_share: float
    reaction_share: float
    speed_share: float
    pauses_share: float


@dataclass(frozen=True)
class VocabularyShares:
    """Quanto cada parte pesou no vocabulário de uma tentativa com vocabulário medido."""

    judged_share: float
    diversity_share: float
    range_share: float


@dataclass(frozen=True)
class ReportScoring:
    """O que o relatório precisa para explicar a conta da nota, sem repetir fórmula na tela."""

    passing_score: int
    fluency: FluencyShares | None
    vocabulary: VocabularyShares | None


@dataclass(frozen=True)
class AttemptReport:
    """O relatório de uma tentativa concluída: a tentativa, os erros, as medidas e a conta."""

    attempt: Attempt
    mistakes: list[ReviewOccurrence]
    speech_metrics: SessionSpeechMetrics | None
    scoring: ReportScoring


def build_attempt_report(attempt: Attempt) -> AttemptReport:
    """Monta o relatório de uma tentativa concluída.

    As medidas de fala são recalculadas das vezes gravadas pelo mesmo serviço que a avaliação
    usou, e não lidas de um número guardado: assim o relatório nunca diverge do que entrou na
    nota. Só aparecem as medidas que o nível da tentativa usa — no nível 1, por exemplo, só a
    reação —, para a tela não mostrar um número que não pesou em nada.
    """
    rules = rules_for_level(attempt.level.order)
    names = ScenarioRole.objects.filter(scenario=attempt.scenario).values_list(
        "persona__name", flat=True
    )
    metrics = session_metrics(list(attempt.speech_turns.all()), excluded_names=list(names))
    shown = _metrics_used_by_level(metrics, rules)
    return AttemptReport(
        attempt=attempt,
        mistakes=attempt_mistakes(attempt),
        speech_metrics=shown,
        scoring=ReportScoring(
            passing_score=PASSING_SCORE,
            fluency=_fluency_shares(shown, rules),
            vocabulary=_vocabulary_shares(shown, rules),
        ),
    )


def _metrics_used_by_level(
    metrics: SessionSpeechMetrics | None, rules: LevelSpeechRules
) -> SessionSpeechMetrics | None:
    """As medidas da sessão sem as que o nível não usa; vazia quando não sobra nenhuma."""
    if metrics is None:
        return None
    fluency, vocabulary = rules.fluency, rules.vocabulary
    shown = SessionSpeechMetrics(
        reaction_seconds=metrics.reaction_seconds,
        words_per_minute=metrics.words_per_minute if fluency.speed is not None else None,
        long_pauses_per_100_words=(
            metrics.long_pauses_per_100_words if fluency.pauses is not None else None
        ),
        lexical_diversity=metrics.lexical_diversity if vocabulary.diversity_share > 0 else None,
        lexical_range=metrics.lexical_range if vocabulary.range_share > 0 else None,
        word_count=metrics.word_count,
    )
    measured = (
        shown.reaction_seconds,
        shown.words_per_minute,
        shown.long_pauses_per_100_words,
        shown.lexical_diversity,
        shown.lexical_range,
    )
    return shown if any(value is not None for value in measured) else None


def _fluency_shares(
    metrics: SessionSpeechMetrics | None, rules: LevelSpeechRules
) -> FluencyShares | None:
    """As proporções da fluência, quando ela foi medida (há tempo de reação)."""
    if metrics is None or metrics.reaction_seconds is None:
        return None
    fluency = rules.fluency
    return FluencyShares(
        measured_share=MEASURED_FLUENCY_SHARE,
        reaction_share=fluency.reaction_share,
        speed_share=fluency.speed_share,
        pauses_share=fluency.pauses_share,
    )


def _vocabulary_shares(
    metrics: SessionSpeechMetrics | None, rules: LevelSpeechRules
) -> VocabularyShares | None:
    """As proporções do vocabulário, quando ele foi medido (há diversidade no nível)."""
    if metrics is None or metrics.lexical_diversity is None:
        return None
    vocabulary = rules.vocabulary
    return VocabularyShares(
        judged_share=vocabulary.judged_share,
        diversity_share=vocabulary.diversity_share,
        range_share=vocabulary.range_share,
    )
