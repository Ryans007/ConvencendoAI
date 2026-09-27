from django.db import migrations

INTERVIEW_LEVEL_ONE_CLOSING_HINT = (
    "The interview is nearly over. Ask the student one last closed question about the "
    "job, answerable with yes or no — for example, whether they can start next month."
)


def seed_interview_level_one_closing_hint(apps, schema_editor):
    """Cria ou atualiza a dica de fechamento própria do nível 1 da entrevista.

    A dica padrão do cenário ("Do you have any questions for us?") abre espaço para os
    critérios de fazer perguntas, que só se aplicam aos níveis 2 e 3. No nível 1 o único
    critério é responder com clareza às perguntas de sim ou não, então o fechamento
    também precisa ser uma pergunta fechada.
    """
    Scenario = apps.get_model("catalog", "Scenario")
    Level = apps.get_model("catalog", "Level")
    ScenarioLevelHint = apps.get_model("catalog", "ScenarioLevelHint")

    ScenarioLevelHint.objects.update_or_create(
        scenario=Scenario.objects.get(slug="entrevista-de-emprego"),
        level=Level.objects.get(order=1),
        defaults={"closing_hint_override": INTERVIEW_LEVEL_ONE_CLOSING_HINT},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_seed_criteria"),
    ]

    operations = [
        migrations.RunPython(seed_interview_level_one_closing_hint, migrations.RunPython.noop),
    ]
