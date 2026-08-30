PASSING_SCORE = 70


def is_passing_score(score: int) -> bool:
    """Nota mínima de aprovação: única, igual para todos os cenários e níveis."""
    return score >= PASSING_SCORE
