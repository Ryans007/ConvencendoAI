from django.db import transaction
from django.utils import timezone

from apps.review.models import ReviewItem, ReviewResult, ReviewResultKind


class ItemAlreadyArchived(Exception):
    """O item já estava arquivado quando o descarte chegou, por exemplo num toque duplicado."""


def discard_item(item: ReviewItem) -> ReviewResult:
    """Arquiva o item e termina a revisão dele como "descartado", sem mexer no calendário.

    O aluno disse que não falou aquilo, então não há o que revisar: a caixa e o vencimento
    ficam como estavam, e as respostas em aberto passam a apontar para o resultado
    "descartado", para a auditoria ver a revisão que ficou pela metade. A trava no item
    impede que dois descartes simultâneos gravem dois resultados.
    """
    with transaction.atomic():
        locked = ReviewItem.objects.select_for_update().get(pk=item.pk)
        if locked.archived_at is not None:
            raise ItemAlreadyArchived(locked.pk)
        result = ReviewResult.objects.create(
            item=locked,
            outcome=ReviewResultKind.DISCARDED,
            box_before=locked.box,
            box_after=locked.box,
            due_on_after=None,
        )
        locked.answers.filter(result__isnull=True).update(result=result)
        locked.archived_at = timezone.now()
        locked.save(update_fields=["archived_at", "updated_at"])
    return result
