from django.db import migrations


def seed_archetypes_and_levels(apps, schema_editor):
    """Cria ou atualiza, por nome e por ordem, os seis arquétipos e os três níveis.

    O nível 3 (produção livre) recebe a linguagem, o ritmo e os pesos já validados
    em teste com falante B1 real. Os níveis 1 e 2 são conteúdo novo, sem teste com
    usuário: ponto de partida documentado como pendente de calibragem.
    """
    Archetype = apps.get_model("catalog", "Archetype")
    Level = apps.get_model("catalog", "Level")
    LevelDefaultWeight = apps.get_model("catalog", "LevelDefaultWeight")

    archetypes = {
        "Gatekeeper": "Controla o acesso a algo que o aluno quer; resiste até ser "
        "convencido pela comunicação, nunca pelo conteúdo técnico.",
        "Avaliador": "Julga o desempenho do aluno dentro da cena; questiona escolhas "
        "e cobra justificativa.",
        "Aliado": "Está do lado do aluno na cena; apoia quando o argumento é bom, "
        "mas não resolve a tarefa por ele.",
        "Adversário": "Se opõe abertamente ao que o aluno quer; precisa ser "
        "convencido ou contornado.",
        "Autoridade": "Tem o poder de decidir; concede quando as condições dela são "
        "atendidas.",
        "Par": "Está no mesmo nível hierárquico do aluno; colabora ou negocia de "
        "igual para igual.",
    }
    for name, description in archetypes.items():
        Archetype.objects.update_or_create(name=name, defaults={"description": description})

    levels = [
        {
            "order": 1,
            "name": "Ouvir",
            "expected_production": "Compreensão auditiva: responde perguntas fechadas "
            "com sim, não ou uma escolha simples.",
            "language": "Use very simple English with short sentences. Ask only "
            "yes/no or two-option questions.",
            "questions": "Ask exactly one closed question per turn, answerable with "
            "yes, no, or a simple choice.",
            "rephrasing": "If the student hesitates, offer the same question with "
            "even simpler wording or two clear options.",
            "concession_pace": "Concede after 2 clear answers that satisfy the "
            "question.",
            "scaffolding_enabled": True,
            "hints": "always",
            "max_turns": 14,
            "expected_cefr": "A1-A2",
            "weights": {
                "objective": 45,
                "fluency": 10,
                "vocabulary": 5,
                "grammar": 5,
                "pronunciation": 10,
                "pragmatics": 20,
                "autonomy": 5,
            },
        },
        {
            "order": 2,
            "name": "Frases curtas",
            "expected_production": "Produção controlada: respostas em frases curtas.",
            "language": "Use simple English, slightly more varied than level 1. "
            "Short-phrase answers are expected.",
            "questions": "Ask one main question per turn that invites a short "
            "phrase, not just yes or no.",
            "rephrasing": "If the student's answer is very short or unclear, "
            "rephrase once in simpler words.",
            "concession_pace": "Concede after 2 or 3 reasonable short-phrase "
            "attempts.",
            "scaffolding_enabled": True,
            "hints": "when_stuck",
            "max_turns": 13,
            "expected_cefr": "A2-B1",
            "weights": {
                "objective": 35,
                "fluency": 15,
                "vocabulary": 10,
                "grammar": 10,
                "pronunciation": 10,
                "pragmatics": 15,
                "autonomy": 5,
            },
        },
        {
            "order": 3,
            "name": "Conversa livre",
            "expected_production": "Produção livre: conversa consolidada, sem "
            "restrição de formato de resposta.",
            "language": "Use simple A2-B1 English: everyday words, short sentences, "
            "no idioms and no jargon. Maximum 15 words per turn.",
            "questions": "Ask exactly ONE short question per turn. Never two.",
            "rephrasing": "If the student's answer is short, hesitant or unclear, "
            "rephrase your question in even simpler words, or offer two options "
            "for them to choose from.",
            "concession_pace": "Concede after 2 reasonable attempts from the "
            "student.",
            "scaffolding_enabled": True,
            "hints": "always",
            "max_turns": 12,
            "expected_cefr": "A2-B1",
            "weights": {
                "objective": 30,
                "fluency": 15,
                "vocabulary": 15,
                "grammar": 15,
                "pronunciation": 10,
                "pragmatics": 10,
                "autonomy": 5,
            },
        },
    ]

    for entry in levels:
        weights = entry.pop("weights")
        level, _ = Level.objects.update_or_create(order=entry["order"], defaults=entry)
        for dimension, weight in weights.items():
            LevelDefaultWeight.objects.update_or_create(
                level=level, dimension=dimension, defaults={"weight": weight}
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_criterion"),
    ]

    operations = [
        migrations.RunPython(seed_archetypes_and_levels, migrations.RunPython.noop),
    ]
