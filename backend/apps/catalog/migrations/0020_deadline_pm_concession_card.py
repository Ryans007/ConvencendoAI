from django.db import migrations

SLUG = "negociar-prazo"
PERSONA = "Rachel"

OLD = (
    "só aceita estender o prazo depois de ouvir um motivo técnico concreto e uma alternativa "
    "de faseamento; então confirma o novo prazo explicitamente"
)
NEW = (
    "aceita estender o prazo assim que o aluno diz duas coisas: (1) o que causa o atraso, por "
    "exemplo uma parte do trabalho que falta e quanto tempo ela leva; e (2) o que entrega em "
    "cada data, em fases. Não pede mais detalhe técnico do que isso. Então confirma o novo "
    "prazo explicitamente"
)


def rewrite_card(apps, schema_editor):
    """Reescreve a condição de concessão da PM em duas partes que se podem verificar.

    "Motivo técnico concreto" é subjetivo: medido com o modelo real, a PM entendia que sempre
    faltava detalhe e perguntava de novo o que o aluno já tinha dito, sem nunca conceder. O texto
    novo diz o que basta. Só é trocado quando ainda é exatamente o da carga inicial, para nunca
    sobrescrever o que o administrador tenha editado.
    """
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(
        scenario__slug=SLUG, persona__name=PERSONA, concession=OLD
    ).update(concession=NEW)


def restore_card(apps, schema_editor):
    """Devolve o texto anterior, só onde o cartão ainda é exatamente o desta migration."""
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(
        scenario__slug=SLUG, persona__name=PERSONA, concession=NEW
    ).update(concession=OLD)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0019_level_three_language"),
    ]

    operations = [
        migrations.RunPython(rewrite_card, restore_card),
    ]
