from apps.progress.models import AttemptCriterion, ScoreBreakdown


def objective_score(criteria: list[AttemptCriterion], weight: int) -> float:
    """Nota da dimensão objetivo: fração de critérios cumpridos vezes o peso efetivo.

    Uma decisão discreta por critério, somada e normalizada em código — nunca uma
    impressão geral estimada pelo modelo de linguagem.
    """
    if not criteria:
        return 0.0
    met_count = sum(1 for criterion in criteria if criterion.met)
    return (met_count / len(criteria)) * weight


def final_score(breakdowns: list[ScoreBreakdown]) -> float:
    """Soma normalizada sobre as dimensões efetivamente avaliadas.

    Uma dimensão ausente do conjunto — por exemplo, pronúncia fora do modo de voz —
    não penaliza: o total é recalculado sobre o peso das dimensões que de fato
    entraram na avaliação.
    """
    achieved = sum(breakdown.value for breakdown in breakdowns)
    possible = sum(breakdown.weight_at_time for breakdown in breakdowns)
    if possible == 0:
        return 0.0
    return (achieved / possible) * 100
