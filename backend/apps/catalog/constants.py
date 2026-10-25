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


class RolePresence(models.TextChoices):
    """Quanto um papel aparece na cena.

    O principal conduz rodadas e entra no rodízio do equilíbrio de turno. O coadjuvante só
    entra quando há motivo (o aluno o chama, o assunto é dele, uma principal se dirige a ele
    ou a aparição garantida), fala curto e nunca conduz a cena: é o terceiro personagem que
    dá um fato ou um apoio pontual sem dividir a conversa por igual com os outros dois.
    """

    PRINCIPAL = "principal", "Principal"
    SUPPORTING = "supporting", "Coadjuvante"
