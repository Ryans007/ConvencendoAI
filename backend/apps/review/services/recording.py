from collections.abc import Sequence
from datetime import date

from apps.agents.services.evaluator import MAX_REVIEW_ITEMS, KnownRule
from apps.agents.services.schemas import ReviewItem as ReportedMistake
from apps.progress.models import Attempt
from apps.review.models import ReviewItem, ReviewOccurrence
from apps.review.services.schedule import restart

_ID_PREFIX = "r"


def known_rule_id(item: ReviewItem) -> str:
    """O identificador com que o avaliador cita um item que o aluno já tem."""
    return f"{_ID_PREFIX}{item.pk}"


def known_rules_for(user) -> list[KnownRule]:
    """As regras que o aluno já tem, para o avaliador reconhecer quando um erro se repete.

    Entram também os itens dominados: errar de novo numa regra dominada é sinal de que ela
    precisa voltar, e não de que é uma regra nova.
    """
    items = ReviewItem.objects.filter(user=user).only("id", "rule").order_by("id")
    return [KnownRule(id=known_rule_id(item), rule=item.rule) for item in items]


def record_review_items(
    user, attempt: Attempt, mistakes: Sequence[ReportedMistake], today: date
) -> list[ReviewItem]:
    """Grava os erros de uma sessão como ocorrências de itens de revisão do aluno.

    Um erro que repete uma regra que o aluno já tem vira uma nova ocorrência daquele item e
    o faz voltar à primeira caixa, inclusive se estava dominado: errar de novo mostra que a
    regra não está firme, e também se o aluno o tinha arquivado com "Não disse isso": o
    arquivamento dizia que ele não falou aquilo, e agora o avaliador ouviu de novo. Um erro
    de regra nova cria um item. Dois erros da mesma regra nova
    na mesma sessão viram um item só, comparando a regra sem diferença de caixa e de espaços.
    Chamado dentro da transação que grava a tentativa: ou tudo é gravado, ou nada.
    """
    known = {known_rule_id(item): item for item in ReviewItem.objects.filter(user=user)}
    created_in_session: dict[str, ReviewItem] = {}
    touched: list[ReviewItem] = []

    for mistake in list(mistakes)[:MAX_REVIEW_ITEMS]:
        box, due_on = restart(today)
        item = known.get(mistake.repeats)
        if item is None:
            key = " ".join(mistake.rule.lower().split())
            item = created_in_session.get(key)
            if item is None:
                item = ReviewItem.objects.create(
                    user=user, rule=mistake.rule, box=box, due_on=due_on
                )
                created_in_session[key] = item
        else:
            item.box, item.due_on, item.archived_at = box, due_on, None
            item.save(update_fields=["box", "due_on", "archived_at", "updated_at"])

        ReviewOccurrence.objects.create(
            item=item,
            attempt=attempt,
            produced=mistake.produced,
            correct=mistake.correct,
            note=mistake.note,
        )
        if item not in touched:
            touched.append(item)

    return touched
