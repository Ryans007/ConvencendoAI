from apps.progress.models import AttemptCriterion, ScoreBreakdown
from apps.progress.services import final_score, objective_score


def test_dois_de_quatro_criterios_cumpridos_produz_metade_do_peso() -> None:
    """Dois de quatro critérios cumpridos com peso 30 produzem 15."""
    criteria = [
        AttemptCriterion(code="c1", text_at_time="...", met=True),
        AttemptCriterion(code="c2", text_at_time="...", met=True),
        AttemptCriterion(code="c3", text_at_time="...", met=False),
        AttemptCriterion(code="c4", text_at_time="...", met=False),
    ]

    assert objective_score(criteria, weight=30) == 15


def test_dimensao_excluida_normaliza_a_nota_sobre_as_restantes() -> None:
    """Excluir uma dimensão da avaliação (pronúncia, fora do modo texto) recalcula o
    total sobre o peso das seis dimensões restantes, em vez de penalizar a ausência.
    """
    breakdowns = [
        ScoreBreakdown(dimension="objective", value=30, weight_at_time=30),
        ScoreBreakdown(dimension="fluency", value=15, weight_at_time=15),
        ScoreBreakdown(dimension="vocabulary", value=15, weight_at_time=15),
        ScoreBreakdown(dimension="grammar", value=15, weight_at_time=15),
        ScoreBreakdown(dimension="pragmatics", value=6, weight_at_time=10),
        ScoreBreakdown(dimension="autonomy", value=0, weight_at_time=5),
    ]

    assert final_score(breakdowns) == 90.0
