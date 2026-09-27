import pytest

from apps.agents.graph import routing as graph_routing
from apps.agents.graph.routing import make_routing_node
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.llm.services.factory import ModelNotConfigured

pytestmark = pytest.mark.django_db


def _content():
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    return load_scenario_content(scenario, level)


def _state(current_speaker: str) -> dict:
    return {
        "messages": [],
        "current_speaker": current_speaker,
        "turn_count": 1,
        "scene_resolved": False,
        "should_end": False,
    }


class _FakeRoutingLLM:
    def __init__(self, decision: RoutingDecision):
        self._decision = decision

    def invoke(self, messages):
        return self._decision


def test_routing_overrides_current_speaker_when_student_addresses_the_other_character(
    monkeypatch,
):
    content = _content()
    current, other = content.role_keys()

    monkeypatch.setattr(
        graph_routing,
        "get_structured_llm",
        lambda purpose, schema: _FakeRoutingLLM(RoutingDecision(speaker=other)),
    )

    node = make_routing_node(content)
    result = node(_state(current))

    assert result == {"current_speaker": other}


def test_routing_keeps_current_speaker_when_student_does_not_address_anyone(monkeypatch):
    content = _content()
    current = content.role_keys()[0]

    monkeypatch.setattr(
        graph_routing,
        "get_structured_llm",
        lambda purpose, schema: _FakeRoutingLLM(RoutingDecision(speaker=current)),
    )

    node = make_routing_node(content)
    result = node(_state(current))

    assert result == {}


def test_routing_keeps_current_speaker_when_model_not_configured(monkeypatch):
    content = _content()
    current = content.role_keys()[0]

    def _raise(purpose, schema):
        raise ModelNotConfigured("nenhum modelo de roteamento configurado")

    monkeypatch.setattr(graph_routing, "get_structured_llm", _raise)

    node = make_routing_node(content)
    result = node(_state(current))

    assert result == {}
