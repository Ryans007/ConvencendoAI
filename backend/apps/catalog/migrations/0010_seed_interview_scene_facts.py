from django.db import migrations

INTERVIEW_SLUG = "entrevista-de-emprego"

SCENE_FACTS = {
    "Rachel": (
        "Fatos da cena, para responder quando o candidato perguntar: a TechCorp é uma "
        "empresa de software de logística com cerca de 200 funcionários, e o trabalho é "
        "híbrido, com dois dias por semana no escritório. A vaga é de desenvolvedor "
        "backend pleno, no time do Tom, com início no mês que vem. O processo seletivo "
        "tem três etapas: esta entrevista, um desafio técnico para fazer em casa em até "
        "cinco dias, e uma conversa final com a gerente de engenharia. O retorno de cada "
        "etapa sai em até uma semana."
    ),
    "Tom": (
        "Fatos da cena, para responder quando o candidato perguntar: o time de backend "
        "tem seis pessoas e cuida das APIs de rastreamento de entregas. A stack é Python "
        "com Django e PostgreSQL, com testes em PyTest e deploy contínuo. Todo pull "
        "request passa por revisão de código, e o time planeja o trabalho a cada duas "
        "semanas. O maior desafio agora é deixar as APIs mais rápidas, porque o volume "
        "de entregas dobrou este ano."
    ),
}


def seed_interview_scene_facts(apps, schema_editor):
    """Cadastra os fatos da TechCorp na instrução extra dos papéis da entrevista.

    Sem esses fatos, a persona improvisa quando o aluno pergunta sobre a vaga, o time ou o
    processo seletivo, e a resposta muda de uma sessão para outra. Cada persona recebe só o
    que a função dela saberia: a RH conhece a empresa e o processo, o tech lead conhece o
    time e a stack. O cadastro fica no papel, e não no contexto do cenário, porque o
    contexto é mostrado ao aluno antes da sessão.
    """
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    for persona_name, facts in SCENE_FACTS.items():
        ScenarioRole.objects.filter(
            scenario__slug=INTERVIEW_SLUG, persona__name=persona_name
        ).update(extra_instruction=facts)


def clear_interview_scene_facts(apps, schema_editor):
    """Esvazia a instrução extra dos dois papéis, voltando ao estado anterior."""
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(
        scenario__slug=INTERVIEW_SLUG, persona__name__in=SCENE_FACTS
    ).update(extra_instruction="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_scenario_max_consecutive_turns"),
    ]

    operations = [
        migrations.RunPython(seed_interview_scene_facts, clear_interview_scene_facts),
    ]
