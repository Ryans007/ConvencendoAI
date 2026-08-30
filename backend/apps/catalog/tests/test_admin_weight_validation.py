import pytest
from django.urls import reverse

from apps.catalog.models import Level, Scenario, Track


@pytest.mark.django_db
def test_admin_recusa_pesos_de_nivel_que_nao_somam_cem(admin_client) -> None:
    """O admin de Level recusa salvar quando a soma dos pesos padrão não é 100."""
    level = Level.objects.get(order=3)
    weights = list(level.default_weights.order_by("id"))

    data = {
        "order": level.order,
        "name": level.name,
        "expected_production": level.expected_production,
        "language": level.language,
        "questions": level.questions,
        "rephrasing": level.rephrasing,
        "concession_pace": level.concession_pace,
        "hints": level.hints,
        "max_turns": level.max_turns,
        "expected_cefr": level.expected_cefr,
        "default_weights-TOTAL_FORMS": str(len(weights)),
        "default_weights-INITIAL_FORMS": str(len(weights)),
        "default_weights-MIN_NUM_FORMS": "0",
        "default_weights-MAX_NUM_FORMS": "1000",
    }
    if level.scaffolding_enabled:
        data["scaffolding_enabled"] = "on"
    for index, weight_row in enumerate(weights):
        data[f"default_weights-{index}-id"] = str(weight_row.id)
        data[f"default_weights-{index}-level"] = str(level.id)
        data[f"default_weights-{index}-dimension"] = weight_row.dimension
        bumped = weight_row.weight + 5 if index == 0 else weight_row.weight
        data[f"default_weights-{index}-weight"] = str(bumped)

    url = reverse("admin:catalog_level_change", args=[level.id])
    response = admin_client.post(url, data)

    assert response.status_code == 200
    level.refresh_from_db()
    assert level.default_weights.get(dimension=weights[0].dimension).weight == weights[0].weight


@pytest.mark.django_db
def test_admin_aceita_pesos_de_nivel_que_somam_cem(admin_client) -> None:
    """O admin de Level salva normalmente quando a soma dos pesos é 100 — a
    validação não pode rejeitar o caso válido, só o inválido.
    """
    level = Level.objects.get(order=3)
    weights = list(level.default_weights.order_by("id"))

    data = {
        "order": level.order,
        "name": level.name,
        "expected_production": level.expected_production,
        "language": level.language,
        "questions": level.questions,
        "rephrasing": level.rephrasing,
        "concession_pace": level.concession_pace,
        "hints": level.hints,
        "max_turns": level.max_turns,
        "expected_cefr": level.expected_cefr,
        "default_weights-TOTAL_FORMS": str(len(weights)),
        "default_weights-INITIAL_FORMS": str(len(weights)),
        "default_weights-MIN_NUM_FORMS": "0",
        "default_weights-MAX_NUM_FORMS": "1000",
    }
    if level.scaffolding_enabled:
        data["scaffolding_enabled"] = "on"
    for index, weight_row in enumerate(weights):
        data[f"default_weights-{index}-id"] = str(weight_row.id)
        data[f"default_weights-{index}-level"] = str(level.id)
        data[f"default_weights-{index}-dimension"] = weight_row.dimension
        data[f"default_weights-{index}-weight"] = str(weight_row.weight)

    url = reverse("admin:catalog_level_change", args=[level.id])
    response = admin_client.post(url, data)

    assert response.status_code == 302


@pytest.mark.django_db
def test_admin_recusa_ajuste_de_peso_que_nao_soma_cem(admin_client) -> None:
    """O admin de Scenario recusa salvar quando o ajuste de peso por nível quebra a
    soma de 100.
    """
    track = Track.objects.get(slug="carreira-em-ti")
    level_3 = Level.objects.get(order=3)

    data = {
        "track": str(track.id),
        "slug": "cenario-teste-admin",
        "title": "Cenário de teste do admin",
        "order": "99",
        "objective": "objetivo",
        "context": "contexto",
        "closing_hint": "Wrap up.",
        "cooldown_hours": "12",
        "criteria-TOTAL_FORMS": "0",
        "criteria-INITIAL_FORMS": "0",
        "criteria-MIN_NUM_FORMS": "0",
        "criteria-MAX_NUM_FORMS": "1000",
        "roles-TOTAL_FORMS": "0",
        "roles-INITIAL_FORMS": "0",
        "roles-MIN_NUM_FORMS": "0",
        "roles-MAX_NUM_FORMS": "1000",
        "level_hints-TOTAL_FORMS": "0",
        "level_hints-INITIAL_FORMS": "0",
        "level_hints-MIN_NUM_FORMS": "0",
        "level_hints-MAX_NUM_FORMS": "1000",
        "level_weight_overrides-TOTAL_FORMS": "1",
        "level_weight_overrides-INITIAL_FORMS": "0",
        "level_weight_overrides-MIN_NUM_FORMS": "0",
        "level_weight_overrides-MAX_NUM_FORMS": "1000",
        "level_weight_overrides-0-level": str(level_3.id),
        "level_weight_overrides-0-dimension": "pragmatics",
        "level_weight_overrides-0-weight": "15",
    }

    response = admin_client.post(reverse("admin:catalog_scenario_add"), data)

    assert response.status_code == 200
    assert not Scenario.objects.filter(slug="cenario-teste-admin").exists()
