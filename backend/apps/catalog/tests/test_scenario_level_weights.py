import pytest
from django.core.exceptions import ValidationError

from apps.catalog.models import Level
from apps.catalog.validators import clean_scenario_level_weights


@pytest.fixture
def nivel_livre(db) -> Level:
    """O nível 3 semeado, com os pesos já validados no núcleo."""
    return Level.objects.get(order=3)


def test_ajuste_parcial_valido_e_aceito(nivel_livre: Level) -> None:
    """Mover peso de vocabulary para pragmatics, mantendo a soma em 100, é aceito."""
    clean_scenario_level_weights(nivel_livre, {"pragmatics": 15, "vocabulary": 10})


def test_ajuste_que_rompe_a_soma_e_recusado(nivel_livre: Level) -> None:
    """Subir pragmatics sem baixar nenhuma outra dimensão produz soma 105 e é recusado."""
    with pytest.raises(ValidationError, match="105"):
        clean_scenario_level_weights(nivel_livre, {"pragmatics": 15})
