from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0002_review_rounds'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewoccurrence',
            name='note',
            field=models.TextField(blank=True, default='', help_text='Frase curta, em português, que diz o que observar na frase sem escrever o inglês correto. Vazia nos itens criados antes de a nota existir.', verbose_name='nota'),
        ),
        migrations.AlterField(
            model_name='reviewoccurrence',
            name='correct',
            field=models.TextField(help_text='A mesma frase corrigida, mantendo o que o aluno quis dizer.', verbose_name='forma correta'),
        ),
        migrations.AlterField(
            model_name='reviewoccurrence',
            name='produced',
            field=models.TextField(help_text='A frase inteira que o aluno disse, com o erro dentro dela.', verbose_name='o aluno disse'),
        ),
    ]
