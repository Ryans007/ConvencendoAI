from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0010_seed_interview_scene_facts'),
    ]

    operations = [
        migrations.AddField(
            model_name='level',
            name='reply_to_student',
            field=models.TextField(default='', help_text='Instrução em inglês para a persona: como ela responde quando o aluno faz uma pergunta ou um comentário a ela, e como devolve a vez depois.', verbose_name='como responder ao aluno'),
            preserve_default=False,
        ),
    ]
