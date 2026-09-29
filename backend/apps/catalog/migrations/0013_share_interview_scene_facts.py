from django.db import migrations

INTERVIEW_SLUG = "entrevista-de-emprego"

COMPANY_AND_PROCESS_FACTS = (
    "a TechCorp é uma empresa de software de logística com cerca de 200 funcionários, e o "
    "trabalho é híbrido, com dois dias por semana no escritório. A vaga é de "
    "desenvolvedor backend pleno, no time do Tom, com início no mês que vem. O processo "
    "seletivo tem três etapas: esta entrevista, um desafio técnico para fazer em casa em "
    "até cinco dias, e uma conversa final com a gerente de engenharia. O retorno de cada "
    "etapa sai em até uma semana."
)

TEAM_FACTS = (
    "O time de backend tem seis pessoas e cuida das APIs de rastreamento de entregas. A "
    "stack é Python com Django e PostgreSQL, com testes em PyTest e deploy contínuo. Todo "
    "pull request passa por revisão de código, e o time planeja o trabalho a cada duas "
    "semanas. O maior desafio agora é deixar as APIs mais rápidas, porque o volume de "
    "entregas dobrou este ano."
)

SHARED_FACTS = (
    "Fatos da cena, para responder quando o candidato perguntar (você e o outro "
    f"entrevistador conhecem todos eles): {COMPANY_AND_PROCESS_FACTS} {TEAM_FACTS}"
)

SPLIT_FACTS = {
    "Rachel": (
        "Fatos da cena, para responder quando o candidato perguntar: "
        f"{COMPANY_AND_PROCESS_FACTS}"
    ),
    "Tom": f"Fatos da cena, para responder quando o candidato perguntar: {TEAM_FACTS}",
}


def share_interview_scene_facts(apps, schema_editor):
    """Dá aos dois entrevistadores os mesmos fatos da TechCorp.

    Uma pergunta do aluno feita sem nome vai para quem está falando com ele. Com os fatos
    divididos por função, o entrevistador que não tinha o fato inventava uma resposta que
    contradizia o cadastro: a RH dizia um tamanho de time qualquer, e o tech lead
    inventava as etapas do processo. Numa entrevista real os dois sabem o básico de tudo
    isso, então cada papel passa a carregar o texto inteiro.
    """
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(
        scenario__slug=INTERVIEW_SLUG, persona__name__in=SPLIT_FACTS
    ).update(extra_instruction=SHARED_FACTS)


def split_interview_scene_facts(apps, schema_editor):
    """Volta à divisão por função: a RH com a empresa e o processo, o tech lead com o time."""
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    for persona_name, facts in SPLIT_FACTS.items():
        ScenarioRole.objects.filter(
            scenario__slug=INTERVIEW_SLUG, persona__name=persona_name
        ).update(extra_instruction=facts)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_seed_level_reply_to_student"),
    ]

    operations = [
        migrations.RunPython(share_interview_scene_facts, split_interview_scene_facts),
    ]
