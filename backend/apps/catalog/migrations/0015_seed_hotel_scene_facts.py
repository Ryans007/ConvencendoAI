from django.db import migrations

HOTEL_SLUG = "problema-no-quarto"
HOTEL_PERSONAS = ("Emma", "James")

HOTEL_FACTS = (
    "Fatos da cena, para responder quando o hóspede perguntar (você e o outro personagem "
    "conhecem todos eles): a manutenção do hotel conserta o ar-condicionado hoje mesmo, e "
    "o conserto leva cerca de uma hora, a partir do momento em que o técnico sobe. O "
    "hóspede pode trocar de quarto sem nenhum custo extra: há quartos livres no terceiro "
    "e no quinto andar, e a troca fica pronta em cerca de vinte minutos. Enquanto o quarto "
    "é consertado, o hóspede pode sair e voltar depois, ou esperar no saguão. O hotel não "
    "oferece reembolso nem desconto na diária por esse problema, e nenhum de vocês dois "
    "tem autorização para prometer isso."
)


def seed_hotel_scene_facts(apps, schema_editor):
    """Dá à Emma e ao James do hotel os mesmos fatos sobre o que o hotel oferece.

    Uma pergunta do aluno feita sem nome vai para quem está falando com ele, então os dois
    precisam saber o mesmo: sem fatos, o James ofereceu um reembolso que o cenário nunca
    previu. O texto só entra em papéis sem instrução extra, para nunca sobrescrever o que
    o administrador tenha escrito à mão.
    """
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(
        scenario__slug=HOTEL_SLUG, persona__name__in=HOTEL_PERSONAS, extra_instruction=""
    ).update(extra_instruction=HOTEL_FACTS)


def clear_hotel_scene_facts(apps, schema_editor):
    """Limpa os fatos do hotel, só nos papéis cujo texto ainda é exatamente o desta carga."""
    ScenarioRole = apps.get_model("catalog", "ScenarioRole")

    ScenarioRole.objects.filter(
        scenario__slug=HOTEL_SLUG,
        persona__name__in=HOTEL_PERSONAS,
        extra_instruction=HOTEL_FACTS,
    ).update(extra_instruction="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0014_remove_level_hints"),
    ]

    operations = [
        migrations.RunPython(seed_hotel_scene_facts, clear_hotel_scene_facts),
    ]
