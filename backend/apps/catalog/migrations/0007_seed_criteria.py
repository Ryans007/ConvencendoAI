from django.db import migrations


def seed_criteria(apps, schema_editor):
    """Semeia os critérios de aceite dos três cenários já validados.

    Os quatro critérios de cada cenário são os validados em teste com falante B1
    real, e valem nos níveis 2 e 3 (que exigem produção). O critério de código
    "c5" de cada cenário é conteúdo NOVO, ainda não validado em teste com
    usuário: uma primeira tentativa de critério de compreensão para o nível 1,
    pendente de calibragem.
    """
    Scenario = apps.get_model("catalog", "Scenario")
    Criterion = apps.get_model("catalog", "Criterion")
    Level = apps.get_model("catalog", "Level")

    level_1 = Level.objects.get(order=1)
    production_levels = list(Level.objects.filter(order__in=[2, 3]))

    validated_criteria = {
        "entrevista-de-emprego": [
            ("c1", "Apresentou sua experiência profissional com ao menos um exemplo concreto"),
            ("c2", "Explicou uma decisão técnica que tomou e a justificativa dela"),
            ("c3", "Fez ao menos uma pergunta sobre a vaga, o time ou a empresa"),
            ("c4", "Perguntou sobre os próximos passos do processo seletivo"),
        ],
        "negociar-prazo": [
            ("c1", "Explicou o motivo técnico concreto do atraso"),
            (
                "c2",
                "Quantificou o impacto de manter o prazo original (risco, bugs, dívida)",
            ),
            (
                "c3",
                "Propôs uma alternativa concreta (entrega parcial, corte de escopo, "
                "faseamento)",
            ),
            ("c4", "Obteve da Rachel uma confirmação explícita do novo prazo"),
        ],
        "problema-no-quarto": [
            ("c1", "Explicou claramente qual é o problema do quarto"),
            ("c2", "Informou o número do quarto ou em que andar está"),
            ("c3", "Pediu uma solução concreta (trocar de quarto ou consertar hoje)"),
            ("c4", "Confirmou o que a recepção vai fazer e quando"),
        ],
    }

    comprehension_criteria = {
        "entrevista-de-emprego": (
            "c5",
            "Respondeu de forma clara e coerente às perguntas de sim ou não feitas "
            "pelos entrevistadores",
        ),
        "negociar-prazo": (
            "c5",
            "Respondeu de forma clara e coerente às perguntas de sim ou não feitas "
            "por Rachel e Tom sobre o andamento do trabalho",
        ),
        "problema-no-quarto": (
            "c5",
            "Respondeu de forma clara e coerente às perguntas de sim ou não feitas "
            "pela recepção sobre o problema do quarto",
        ),
    }

    for slug, criteria in validated_criteria.items():
        scenario = Scenario.objects.get(slug=slug)
        for order, (code, text) in enumerate(criteria, start=1):
            criterion, _ = Criterion.objects.update_or_create(
                scenario=scenario, code=code, defaults={"text": text, "order": order}
            )
            criterion.levels.set(production_levels)

        code, text = comprehension_criteria[slug]
        criterion, _ = Criterion.objects.update_or_create(
            scenario=scenario,
            code=code,
            defaults={"text": text, "order": len(criteria) + 1},
        )
        criterion.levels.set([level_1])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_seed_validated_tracks"),
    ]

    operations = [
        migrations.RunPython(seed_criteria, migrations.RunPython.noop),
    ]
