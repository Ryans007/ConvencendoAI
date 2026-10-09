from datetime import date

from django.utils import timezone

from apps.review.services.queries import active_items
from apps.review.services.schedule import FIRST_BOX


def make_items_due(user, today: date, restart_boxes: bool = False) -> int:
    """Deixa todos os itens ativos do aluno vencidos hoje e devolve quantos mudaram.

    Existe para testar a revisão sem esperar os dias do calendário: o aluno real nunca
    precisa disso, porque o vencimento só muda por uma resposta dele. Com `restart_boxes`,
    os itens também voltam para a primeira caixa, para repetir o ciclo desde o início. Os
    itens arquivados ficam como estão, porque saíram da revisão por escolha do aluno.
    """
    changes = {"due_on": today, "updated_at": timezone.now()}
    if restart_boxes:
        changes["box"] = FIRST_BOX
    return active_items(user).update(**changes)
