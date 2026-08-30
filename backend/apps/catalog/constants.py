from django.db import models


class RubricDimension(models.TextChoices):
    """As sete dimensões da rúbrica de avaliação.

    Fica fora de `models.py` porque é referenciada tanto pelo catálogo (peso padrão de
    um nível, ajuste de cenário) quanto pela progressão (sub-nota de uma tentativa), e
    nenhum dos dois deveria importar o outro só para alcançar este enum. A soma dos
    pesos efetivos das sete, em qualquer combinação de cenário e nível, deve ser 100.
    """

    OBJECTIVE = "objective", "Objetivo"
    FLUENCY = "fluency", "Fluência"
    VOCABULARY = "vocabulary", "Vocabulário"
    GRAMMAR = "grammar", "Gramática"
    PRONUNCIATION = "pronunciation", "Pronúncia"
    PRAGMATICS = "pragmatics", "Pragmática"
    AUTONOMY = "autonomy", "Autonomia"
