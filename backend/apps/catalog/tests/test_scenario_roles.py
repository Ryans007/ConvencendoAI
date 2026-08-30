import pytest

from apps.catalog.models import Archetype, Level, Persona, Scenario, ScenarioRole, Track


@pytest.fixture
def persona(db) -> Persona:
    return Persona.objects.create(name="Rachel", voice="hannah")


@pytest.fixture
def track(db) -> Track:
    return Track.objects.create(
        slug="carreira-em-ti-teste",
        title="Carreira em TI (teste)",
        order=900,
        student_role="dev backend",
    )


def _scenario(track: Track, slug: str, order: int) -> Scenario:
    return Scenario.objects.create(
        track=track,
        slug=slug,
        title=slug,
        order=order,
        objective="objetivo",
        context="contexto",
        closing_hint="Wrap up the scene.",
    )


def test_mesma_persona_muda_de_papel_entre_cenarios(persona: Persona, track: Track) -> None:
    """A persona mantém nome e voz ao exercer papéis diferentes em dois cenários."""
    gatekeeper = Archetype.objects.get(name="Gatekeeper")
    autoridade = Archetype.objects.get(name="Autoridade")

    interview = _scenario(track, "entrevista-teste", 1)
    negotiation = _scenario(track, "negociar-prazo-teste", 2)

    role_in_interview = ScenarioRole.objects.create(
        scenario=interview,
        persona=persona,
        archetype=gatekeeper,
        scene_function="recrutadora de RH",
        traits="cordial mas objetiva",
        resistance="pede exemplos concretos",
        concession="fica satisfeita com exemplos específicos",
        opening_order=1,
    )
    role_in_negotiation = ScenarioRole.objects.create(
        scenario=negotiation,
        persona=persona,
        archetype=autoridade,
        scene_function="gerente de produto",
        traits="direta, pressionada pelo trimestre",
        resistance="não concede no primeiro pedido",
        concession="aceita depois de um motivo técnico concreto",
        opening_order=1,
    )

    assert role_in_interview.persona_id == role_in_negotiation.persona_id
    assert role_in_interview.persona.name == "Rachel"
    assert role_in_interview.persona.voice == role_in_negotiation.persona.voice
    assert role_in_interview.scene_function != role_in_negotiation.scene_function


def test_apoio_e_reconhecido_por_nivel_e_independe_do_arquetipo(
    persona: Persona, track: Track
) -> None:
    """Um papel com arquétipo diferente de 'Aliado' pode apoiar o aluno num nível."""
    authority = Archetype.objects.get(name="Autoridade")
    level_one = Level.objects.get(order=1)
    scenario = _scenario(track, "hotel", 1)

    role = ScenarioRole.objects.create(
        scenario=scenario,
        persona=persona,
        archetype=authority,
        scene_function="gerente do hotel",
        traits="prestativa",
        resistance="confirma os fatos antes de agir",
        concession="resolve quando o pedido é claro",
        opening_order=1,
    )
    role.scaffolding_levels.add(level_one)

    assert role.scaffolding_levels.filter(pk=level_one.pk).exists()
    assert role.archetype.name != "Aliado"
