from django.db.models import QuerySet

from apps.catalog.models import Criterion, Level, Scenario


def applicable_criteria(scenario: Scenario, level: Level) -> QuerySet[Criterion]:
    """Critérios de um cenário que se aplicam a um nível específico, na ordem cadastrada.

    Um critério que não declara este nível entre os seus fica de fora: é assim que o
    nível de compreensão evita cobrar produção que o aluno não tem como entregar
    respondendo apenas sim ou não.
    """
    return scenario.criteria.filter(levels=level).order_by("order")
