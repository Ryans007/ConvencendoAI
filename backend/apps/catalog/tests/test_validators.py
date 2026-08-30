import pytest
from django.core.exceptions import ValidationError

from apps.catalog.validators import validate_dimension_weights

_VALID_WEIGHTS = {
    "objective": 30,
    "fluency": 15,
    "vocabulary": 15,
    "grammar": 15,
    "pronunciation": 10,
    "pragmatics": 10,
    "autonomy": 5,
}


def test_soma_cem_e_aceita() -> None:
    """Um conjunto com as sete dimensões somando 100 não levanta exceção."""
    validate_dimension_weights(_VALID_WEIGHTS)


def test_soma_diferente_de_cem_e_recusada() -> None:
    """Elevar uma dimensão sem reduzir outra rompe a soma e é recusado."""
    pesos = {**_VALID_WEIGHTS, "pragmatics": 15}

    with pytest.raises(ValidationError, match="105"):
        validate_dimension_weights(pesos)


def test_dimensao_faltando_e_recusada() -> None:
    """Um conjunto incompleto é recusado, mesmo que o que está presente some 100."""
    pesos = dict(_VALID_WEIGHTS)
    del pesos["autonomy"]

    with pytest.raises(ValidationError, match="autonomy"):
        validate_dimension_weights(pesos)
