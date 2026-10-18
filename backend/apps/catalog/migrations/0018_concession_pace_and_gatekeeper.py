from django.db import migrations

GATEKEEPER_OLD = (
    "Controla o acesso a algo que o aluno quer; resiste até ser convencido pela "
    "comunicação, nunca pelo conteúdo técnico."
)
GATEKEEPER_NEW = (
    "Controla o acesso a algo que o aluno quer; resiste até que o aluno cumpra as "
    "condições do papel, e então cede."
)

PACE_PREFIX = (
    "Concede as soon as the student meets what makes you concede, and at the latest after "
)

PACES = {
    1: (
        "Concede after 2 clear answers that satisfy the question.",
        PACE_PREFIX + "2 clear answers that satisfy the question.",
    ),
    2: (
        "Concede after 2 or 3 reasonable short-phrase attempts.",
        PACE_PREFIX + "2 or 3 reasonable short-phrase attempts.",
    ),
    3: (
        "Concede after 2 reasonable attempts from the student.",
        PACE_PREFIX + "2 reasonable attempts from the student.",
    ),
}


def apply_new_texts(apps, schema_editor):
    """Reescreve o Gatekeeper e o ritmo de concessão dos níveis.

    O Gatekeeper dizia "nunca pelo conteúdo técnico", o que contradiz o cartão da PM, que
    só cede depois de um motivo técnico. O ritmo dos níveis contava tentativas, e um
    argumento completo na primeira tentativa não bastava: agora o ritmo é um limite máximo.
    Cada texto só é trocado quando ainda é exatamente o da carga inicial, para nunca
    sobrescrever o que o administrador tenha editado.
    """
    Archetype = apps.get_model("catalog", "Archetype")
    Level = apps.get_model("catalog", "Level")

    Archetype.objects.filter(name="Gatekeeper", description=GATEKEEPER_OLD).update(
        description=GATEKEEPER_NEW
    )
    for order, (old, new) in PACES.items():
        Level.objects.filter(order=order, concession_pace=old).update(concession_pace=new)


def restore_old_texts(apps, schema_editor):
    """Devolve os textos anteriores, só onde o texto ainda é o desta migration."""
    Archetype = apps.get_model("catalog", "Archetype")
    Level = apps.get_model("catalog", "Level")

    Archetype.objects.filter(name="Gatekeeper", description=GATEKEEPER_NEW).update(
        description=GATEKEEPER_OLD
    )
    for order, (old, new) in PACES.items():
        Level.objects.filter(order=order, concession_pace=new).update(concession_pace=old)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0017_seed_role_decides_outcome"),
    ]

    operations = [
        migrations.RunPython(apply_new_texts, restore_old_texts),
    ]
