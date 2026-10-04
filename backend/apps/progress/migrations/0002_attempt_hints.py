from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('progress', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='attempt',
            name='hints_enabled',
            field=models.BooleanField(default=False, help_text='O aluno começou a sessão com as dicas ligadas.', verbose_name='dicas ligadas'),
        ),
        migrations.AddField(
            model_name='attempt',
            name='hints_used',
            field=models.PositiveSmallIntegerField(default=0, help_text='Quantas dicas o aluno pediu na sessão, no máximo uma por vez dele.', verbose_name='dicas usadas'),
        ),
    ]
