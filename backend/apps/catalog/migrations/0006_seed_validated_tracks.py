from django.db import migrations


def seed_validated_tracks(apps, schema_editor):
    """Semeia as duas trilhas com os três cenários já validados em teste com
    falante B1 real: Entrevista de emprego e Negociar prazo (trilha Carreira em
    TI), e Problema no quarto do hotel (trilha Viagem e Intercâmbio).

    O apoio ao aluno (scaffolding) só é atribuído ao papel de Tom em "Negociar
    prazo", reproduzindo fielmente o comportamento testado: nos outros dois
    cenários, nenhum papel do elenco validado apoia o aluno.
    """
    Track = apps.get_model("catalog", "Track")
    Persona = apps.get_model("catalog", "Persona")
    Scenario = apps.get_model("catalog", "Scenario")
    Archetype = apps.get_model("catalog", "Archetype")
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")
    Level = apps.get_model("catalog", "Level")
    ScenarioLevelWeightOverride = apps.get_model("catalog", "ScenarioLevelWeightOverride")

    career_track, _ = Track.objects.update_or_create(
        slug="carreira-em-ti",
        defaults={
            "title": "Carreira em TI",
            "order": 1,
            "student_role": "Você é um(a) desenvolvedor(a) backend.",
        },
    )
    travel_track, _ = Track.objects.update_or_create(
        slug="viagem-e-intercambio",
        defaults={
            "title": "Viagem e Intercâmbio",
            "order": 2,
            "student_role": "Você está viajando e hospedado em um hotel em Londres.",
        },
    )

    rachel, _ = Persona.objects.update_or_create(name="Rachel", defaults={"voice": "hannah"})
    tom, _ = Persona.objects.update_or_create(name="Tom", defaults={"voice": "daniel"})
    emma, _ = Persona.objects.update_or_create(name="Emma", defaults={"voice": "autumn"})
    james, _ = Persona.objects.update_or_create(name="James", defaults={"voice": "troy"})

    gatekeeper = Archetype.objects.get(name="Gatekeeper")
    appraiser = Archetype.objects.get(name="Avaliador")
    ally = Archetype.objects.get(name="Aliado")
    authority = Archetype.objects.get(name="Autoridade")
    level_3 = Level.objects.get(order=3)

    interview, _ = Scenario.objects.update_or_create(
        slug="entrevista-de-emprego",
        defaults={
            "track": career_track,
            "title": "Entrevista de emprego na TechCorp",
            "order": 1,
            "objective": "Convencer os entrevistadores de que você é a pessoa certa "
            "para a vaga de desenvolvedor backend.",
            "context": "Você se candidatou a uma vaga de dev backend na TechCorp. "
            "Rachel (RH) e Tom (tech lead) conduzem a entrevista.",
            "closing_hint": "The interview is nearly over. If the student has not "
            'asked you anything about the role, the team, the company or the '
            'process yet, invite them now: "Do you have any questions for us?"',
            "cooldown_hours": 12,
        },
    )
    ScenarioRole.objects.update_or_create(
        scenario=interview,
        persona=rachel,
        defaults={
            "archetype": gatekeeper,
            "scene_function": "recrutadora de RH",
            "traits": "cordial mas objetiva; controla o andamento da entrevista",
            "resistance": "não elogia de graça; pede exemplos concretos quando a "
            "resposta é vaga ou genérica",
            "concession": "fica satisfeita quando ouve um exemplo específico com "
            "contexto, ação e resultado",
            "opening_order": 1,
        },
    )
    ScenarioRole.objects.update_or_create(
        scenario=interview,
        persona=tom,
        defaults={
            "archetype": appraiser,
            "scene_function": "tech lead do time de backend",
            "traits": "técnico, curioso, vai a fundo em detalhes de implementação",
            "resistance": 'questiona escolhas técnicas e pergunta "por que não a '
            'alternativa X?"',
            "concession": "aceita a resposta quando o candidato justifica o tradeoff",
            "opening_order": 2,
        },
    )

    negotiation, _ = Scenario.objects.update_or_create(
        slug="negociar-prazo",
        defaults={
            "track": career_track,
            "title": "Negociar prazo com a PM",
            "order": 2,
            "objective": "Conseguir uma semana extra de prazo para entregar o "
            "módulo em que você está trabalhando.",
            "context": "Você já trabalha na TechCorp. O escopo do módulo aumentou "
            "depois do combinado e a entrega original não é viável. Rachel agora é "
            "a PM do produto e Tom é seu tech lead.",
            "closing_hint": "The conversation is nearly over. If the student has "
            "explained the delay and proposed a plan, state the new deadline out "
            "loud and confirm it explicitly with them.",
            "cooldown_hours": 12,
        },
    )
    ScenarioRole.objects.update_or_create(
        scenario=negotiation,
        persona=rachel,
        defaults={
            "archetype": gatekeeper,
            "scene_function": "PM do produto",
            "traits": "direta, pressionada pelo fechamento do trimestre",
            "resistance": "não concede prazo no primeiro pedido; lembra do "
            "compromisso com o cliente e pergunta o que já foi feito",
            "concession": "só aceita estender o prazo depois de ouvir um motivo "
            "técnico concreto e uma alternativa de faseamento; então confirma o "
            "novo prazo explicitamente",
            "opening_order": 1,
        },
    )
    tom_in_negotiation, _ = ScenarioRole.objects.update_or_create(
        scenario=negotiation,
        persona=tom,
        defaults={
            "archetype": ally,
            "scene_function": "tech lead, seu colega",
            "traits": "está do seu lado, mas não peita a PM",
            "resistance": "apoia com dados técnicos se você trouxer o argumento; "
            "não resolve a negociação por você",
            "concession": "reforça seu argumento quando ele é técnico e específico",
            "opening_order": 2,
        },
    )
    tom_in_negotiation.scaffolding_levels.set(Level.objects.all())

    hotel, _ = Scenario.objects.update_or_create(
        slug="problema-no-quarto",
        defaults={
            "track": travel_track,
            "title": "Problema no quarto do hotel",
            "order": 1,
            "objective": "Resolver o problema do ar-condicionado do seu quarto: "
            "trocar de quarto ou conseguir um conserto hoje.",
            "context": "Você está hospedado num hotel em Londres por mais três "
            "noites. O ar-condicionado do seu quarto não funciona e o quarto está "
            "muito quente. Você desce até a recepção, onde Emma atende. James é o "
            "gerente do hotel.",
            "closing_hint": "The conversation is nearly over. Say out loud what "
            "you are going to do and when, so the guest knows exactly what to "
            "expect.",
            "cooldown_hours": 12,
        },
    )
    ScenarioRole.objects.update_or_create(
        scenario=hotel,
        persona=emma,
        defaults={
            "archetype": gatekeeper,
            "scene_function": "recepcionista do hotel",
            "traits": "educada, prestativa, segue o procedimento do hotel",
            "resistance": "primeiro oferece mandar um técnico em vez de trocar o "
            "quarto; pede o número do quarto e os detalhes antes de decidir "
            "qualquer coisa",
            "concession": "concorda em trocar o quarto depois que o hóspede "
            "explica o problema e pede a troca; se o hóspede insistir em falar "
            "com um responsável, chama James",
            "opening_order": 1,
        },
    )
    ScenarioRole.objects.update_or_create(
        scenario=hotel,
        persona=james,
        defaults={
            "archetype": authority,
            "scene_function": "gerente do hotel",
            "traits": "calmo, resolve rápido, quer o hóspede satisfeito",
            "resistance": "pergunta exatamente o que o hóspede prefere antes de "
            "decidir",
            "concession": "autoriza a troca de quarto e confirma o horário",
            "opening_order": 2,
        },
    )

    for scenario in (negotiation, hotel):
        for dimension, weight in {"pragmatics": 15, "vocabulary": 10}.items():
            ScenarioLevelWeightOverride.objects.update_or_create(
                scenario=scenario,
                level=level_3,
                dimension=dimension,
                defaults={"weight": weight},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_seed_archetypes_and_levels"),
    ]

    operations = [
        migrations.RunPython(seed_validated_tracks, migrations.RunPython.noop),
    ]
