from django.db import migrations

DECIDERS = {
    "entrevista-de-emprego": ("Rachel", "Tom"),
    "negociar-prazo": ("Rachel",),
    "problema-no-quarto": ("Emma", "James"),
}


def mark_deciders(apps, schema_editor):
    """Marca, em cada cenário inicial, os papéis que decidem o resultado da cena.

    Na negociação de prazo só a Rachel decide: o Tom é o aliado e apoia o aluno, mas quem
    concede a semana extra e confirma o prazo é a PM. Nos outros dois cenários os dois
    papéis decidem, como já se comportavam. Cenários criados depois pelo administrador não
    são tocados.
    """
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    for slug, names in DECIDERS.items():
        ScenarioRole.objects.filter(scenario__slug=slug, persona__name__in=names).update(
            decides_outcome=True
        )


def unmark_deciders(apps, schema_editor):
    """Desfaz a marca nos papéis dos cenários iniciais, sem tocar nas outras colunas."""
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(scenario__slug__in=list(DECIDERS)).update(decides_outcome=False)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0016_scenario_role_decides_outcome"),
    ]

    operations = [
        migrations.RunPython(mark_deciders, unmark_deciders),
    ]
