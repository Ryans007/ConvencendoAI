import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Level, Scenario, Track
from apps.progress.services import build_journey


@pytest.fixture
def levels(db) -> list[Level]:
    return list(Level.objects.filter(order__in=(1, 2, 3)))


def _scenario(track: Track, slug: str, order: int) -> Scenario:
    return Scenario.objects.create(
        track=track,
        slug=slug,
        title=slug,
        order=order,
        objective="objetivo",
        context="contexto",
        closing_hint="Wrap up the scene.",
    )


@pytest.mark.django_db
def test_leitura_da_jornada_nao_cresce_com_o_numero_de_cenarios(
    django_user_model, levels: list[Level]
) -> None:
    """A quantidade de consultas para montar a jornada inteira não cresce com o
    número de trilhas e cenários existentes.
    """
    user = django_user_model.objects.create(username="aluno")
    track_a = Track.objects.create(slug="a", title="A", order=900, student_role="dev backend")
    _scenario(track_a, "a1", 1)
    _scenario(track_a, "a2", 2)

    with CaptureQueriesContext(connection) as small:
        build_journey(user)

    track_b = Track.objects.create(slug="b", title="B", order=901, student_role="hóspede")
    for i in range(10):
        _scenario(track_b, f"b{i}", i + 1)

    with CaptureQueriesContext(connection) as big:
        build_journey(user)

    assert len(big.captured_queries) == len(small.captured_queries)
