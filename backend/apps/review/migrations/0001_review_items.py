import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('progress', '0002_attempt_hints'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ReviewItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rule', models.CharField(help_text='A regra de inglês que o aluno errou, como o avaliador a escreve, em inglês.', max_length=200, verbose_name='regra')),
                ('box', models.PositiveSmallIntegerField(default=0, help_text='Índice da caixa de intervalo: 0 é a de 1 dia, 6 é a de 120 dias.', verbose_name='caixa')),
                ('due_on', models.DateField(help_text='Dia em que o item fica vencido e entra na revisão.', verbose_name='volta em')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='atualizado em')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_items', to=settings.AUTH_USER_MODEL, verbose_name='aluno')),
            ],
            options={
                'verbose_name': 'item de revisão',
                'verbose_name_plural': 'itens de revisão',
                'ordering': ['due_on', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ReviewOccurrence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('produced', models.TextField(verbose_name='o aluno disse')),
                ('correct', models.TextField(verbose_name='forma correta')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='registrada em')),
                ('attempt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_occurrences', to='progress.attempt', verbose_name='tentativa')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='occurrences', to='review.reviewitem', verbose_name='item')),
            ],
            options={
                'verbose_name': 'ocorrência',
                'verbose_name_plural': 'ocorrências',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='reviewitem',
            index=models.Index(fields=['user', 'due_on'], name='review_item_user_due'),
        ),
    ]
