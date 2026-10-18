from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0015_seed_hotel_scene_facts"),
    ]

    operations = [
        migrations.AddField(
            model_name="scenariorole",
            name="decides_outcome",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Marque o papel que pode conceder o que o aluno quer e encerrar a cena. "
                    "Um aliado, por exemplo, apoia o aluno mas não decide. Se nenhum papel do "
                    "cenário estiver marcado, todos são tratados como quem decide."
                ),
                verbose_name="decide o resultado da cena",
            ),
        ),
    ]
