from django.db import migrations

REPLY_TO_STUDENT_BY_LEVEL = {
    1: (
        "Answer in one short, simple sentence. Then ask this turn's closed question."
    ),
    2: (
        "Answer in one or two short sentences. Then either ask this turn's question, or "
        "invite the student to go on (for example, \"Anything else you'd like to know?\")."
    ),
    3: (
        "Answer with the detail the question needs, in simple English. Then either ask "
        "this turn's question, or invite the student to go on (for example, \"Does that "
        "answer your question?\")."
    ),
}


def seed_level_reply_to_student(apps, schema_editor):
    """Cadastra, em cada nível, como a persona responde ao aluno e devolve a vez.

    No nível de compreensão o aluno precisa de uma pergunta fechada para responder, então a
    persona responde curto e pergunta. Nos níveis de produção ela já sustenta uma conversa
    e escolhe entre perguntar e convidar o aluno a continuar; o convite conta como a
    pergunta da rodada.
    """
    Level = apps.get_model("catalog", "Level")

    for order, text in REPLY_TO_STUDENT_BY_LEVEL.items():
        Level.objects.filter(order=order).update(reply_to_student=text)


def clear_level_reply_to_student(apps, schema_editor):
    """Esvazia o campo nos três níveis, voltando ao estado anterior."""
    Level = apps.get_model("catalog", "Level")

    Level.objects.filter(order__in=REPLY_TO_STUDENT_BY_LEVEL).update(reply_to_student="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_level_reply_to_student"),
    ]

    operations = [
        migrations.RunPython(seed_level_reply_to_student, clear_level_reply_to_student),
    ]
