from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0004_llmmodel_structured_output_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentmodelconfig',
            name='review_voice',
            field=models.CharField(default='hannah', help_text="Voz do botão 'Ouvir' da revisão. É um nome de voz do modelo de síntese de voz configurado acima, como 'hannah' ou 'troy'.", max_length=40, verbose_name='voz da revisão'),
        ),
    ]
