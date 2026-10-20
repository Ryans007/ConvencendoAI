from django.db import migrations, models

PACE_PREFIX = (
    "Concede as soon as the student meets what makes you concede, and at the latest after "
)
PACES = {
    1: PACE_PREFIX + "2 clear answers that satisfy the question.",
    2: PACE_PREFIX + "2 or 3 reasonable short-phrase attempts.",
    3: PACE_PREFIX + "2 reasonable attempts from the student.",
}


def restore_paces(apps, schema_editor):
    """Devolve, ao desfazer a migration, o ritmo de concessão que cada nível tinha.

    O campo sai porque o prompt deixou de empurrar a persona a ceder num turno: medido numa
    sessão real, a persona que já tinha concedido repetia a concessão em todo turno seguinte.
    """
    Level = apps.get_model("catalog", "Level")

    for order, pace in PACES.items():
        Level.objects.filter(order=order).update(concession_pace=pace)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0021_scenario_max_turns"),
    ]

    operations = [
        migrations.AlterField(
            model_name="level",
            name="concession_pace",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(migrations.RunPython.noop, restore_paces),
        migrations.RemoveField(
            model_name="level",
            name="concession_pace",
        ),
    ]
