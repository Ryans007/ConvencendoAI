from django.db import migrations

OLD = (
    "Use simple A2-B1 English: everyday words, short sentences, no idioms and no jargon. "
    "Maximum 15 words per turn."
)
NEW = (
    "Use simple A2-B1 English: everyday words, short sentences, no idioms. Use a technical "
    "term only when the scene needs it. Keep each turn to one or two short, complete "
    "sentences; never drop articles or verbs just to be shorter."
)


def apply_new_language(apps, schema_editor):
    """Troca o limite de 15 palavras do nível 3 por frases curtas e completas.

    O limite rígido gerava inglês telegráfico ("I cannot extend deadline yet"), e "no jargon"
    brigava com a conversa técnica que a cena agora permite. O texto só muda quando ainda é o
    da carga inicial.
    """
    Level = apps.get_model("catalog", "Level")

    Level.objects.filter(order=3, language=OLD).update(language=NEW)


def restore_old_language(apps, schema_editor):
    """Devolve o texto anterior do nível 3, só onde ele ainda é o desta migration."""
    Level = apps.get_model("catalog", "Level")

    Level.objects.filter(order=3, language=NEW).update(language=OLD)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0018_concession_pace_and_gatekeeper"),
    ]

    operations = [
        migrations.RunPython(apply_new_language, restore_old_language),
    ]
