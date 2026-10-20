from datetime import timedelta

from django.db import migrations
from django.utils import timezone

_MAX_ATTEMPTS = 2
_STEP_REPEAT_CORRECTED = 1
_FIRST_BOX = 0
_FIRST_BOX_DAYS = 1
_FAILED = "failed"


def close_items_stuck_after_step_one(apps, schema_editor):
    """Encerra como erro os itens que errariam a etapa 1 e esperavam a etapa 2.

    Pela regra anterior, duas tentativas erradas na etapa 1 levavam à etapa 2, e o item podia
    ficar parado ali com a revisão aberta. Pela regra nova a revisão termina na etapa 1, e um
    item nesse estado ficaria preso: a rodada o mostraria e o envio de resposta o recusaria.
    Cada um recebe o resultado de erro que a regra nova daria, com a primeira caixa e o
    vencimento do dia seguinte, e as respostas abertas, inclusive uma eventual da etapa 2,
    passam a pertencer a esse resultado. Os valores da primeira caixa ficam escritos aqui, e não
    importados do serviço, para a migração não mudar de comportamento se o serviço mudar.
    """
    ReviewItem = apps.get_model("review", "ReviewItem")
    ReviewResult = apps.get_model("review", "ReviewResult")
    ReviewAnswer = apps.get_model("review", "ReviewAnswer")
    due_on = timezone.localdate() + timedelta(days=_FIRST_BOX_DAYS)

    stuck_ids = (
        ReviewAnswer.objects.filter(result__isnull=True, item__archived_at__isnull=True)
        .values_list("item_id", flat=True)
        .distinct()
    )
    for item in ReviewItem.objects.filter(pk__in=list(stuck_ids)):
        open_answers = list(ReviewAnswer.objects.filter(item=item, result__isnull=True))
        first_step = [a for a in open_answers if a.step == _STEP_REPEAT_CORRECTED]
        if len(first_step) < _MAX_ATTEMPTS or any(a.correct for a in first_step):
            continue
        result = ReviewResult.objects.create(
            item=item,
            outcome=_FAILED,
            box_before=item.box,
            box_after=_FIRST_BOX,
            due_on_after=due_on,
        )
        ReviewAnswer.objects.filter(pk__in=[a.pk for a in open_answers]).update(result=result)
        item.box = _FIRST_BOX
        item.due_on = due_on
        item.save(update_fields=["box", "due_on", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("review", "0003_occurrence_note"),
    ]

    operations = [
        migrations.RunPython(close_items_stuck_after_step_one, migrations.RunPython.noop),
    ]
