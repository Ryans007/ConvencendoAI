import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0001_review_items'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewitem',
            name='archived_at',
            field=models.DateTimeField(blank=True, help_text="Quando o aluno marcou 'Não disse isso'. O item arquivado sai das rodadas e da contagem de vencidos, mas continua aqui para auditoria.", null=True, verbose_name='arquivado em'),
        ),
        migrations.CreateModel(
            name='ReviewResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('outcome', models.CharField(choices=[('first_try', 'Acertou de primeira'), ('second_try', 'Acertou na segunda tentativa'), ('failed', 'Errou'), ('discarded', 'Descartado')], max_length=12, verbose_name='resultado')),
                ('box_before', models.PositiveSmallIntegerField(help_text='Índice da caixa do item antes desta revisão.', verbose_name='caixa antes')),
                ('box_after', models.PositiveSmallIntegerField(help_text='Índice da caixa do item depois desta revisão.', verbose_name='caixa depois')),
                ('due_on_after', models.DateField(blank=True, help_text='Novo vencimento do item, ou vazio quando foi descartado.', null=True, verbose_name='vence em')),
                ('finished_at', models.DateTimeField(auto_now_add=True, verbose_name='terminada em')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='review.reviewitem', verbose_name='item')),
            ],
            options={
                'verbose_name': 'resultado da revisão',
                'verbose_name_plural': 'resultados da revisão',
                'ordering': ['-finished_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ReviewAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step', models.PositiveSmallIntegerField(help_text='1 é falar a frase corrigida, 2 é falar uma frase nova com a mesma estrutura.', verbose_name='etapa')),
                ('attempt', models.PositiveSmallIntegerField(help_text='1 ou 2: cada etapa aceita até duas tentativas.', verbose_name='tentativa')),
                ('heard', models.TextField(help_text='A transcrição da fala do aluno.', verbose_name='ouvimos')),
                ('correct', models.BooleanField(help_text='Se o professor considerou a resposta certa.', verbose_name='certa')),
                ('feedback', models.TextField(help_text='O feedback em português que o aluno viu.', verbose_name='feedback do professor')),
                ('correction', models.TextField(blank=True, help_text='A frase do aluno corrigida, em inglês, quando a resposta estava errada.', verbose_name='correção do professor')),
                ('revealed_correct', models.TextField(blank=True, help_text='A forma correta que a tela mostrou depois desta resposta, ou vazio.', verbose_name='forma correta mostrada')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='respondida em')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='review.reviewitem', verbose_name='item')),
                ('result', models.ForeignKey(blank=True, help_text='Vazio enquanto a revisão do item não terminou.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answers', to='review.reviewresult', verbose_name='resultado')),
            ],
            options={
                'verbose_name': 'resposta da revisão',
                'verbose_name_plural': 'respostas da revisão',
                'ordering': ['created_at', 'id'],
            },
        ),
    ]
