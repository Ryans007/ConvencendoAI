from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0013_share_interview_scene_facts'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='level',
            name='hints',
        ),
    ]
