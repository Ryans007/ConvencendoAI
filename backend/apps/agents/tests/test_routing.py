import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import routing as graph_routing
from apps.agents.graph.routing import NO_ADDRESSEE, make_routing_node
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.llm.services.factory import ModelNotConfigured

pytestmark = pytest.mark.django_db


class _FakeRoutingLLM:
    def __init__(self, decision: RoutingDecision):
        self._decision = decision

    def invoke(self, messages):
        return self._decision


class _FixedDraw:
    def __init__(self, value: int):
        self.value = value

    def randint(self, low: int, high: int) -> int:
        return self.value


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )


def _history(name: str, rounds: int) -> list:
    """Histórico em que `name` conduziu as últimas `rounds` rodadas seguidas."""
    history = []
    for _ in range(rounds):
        history += [AIMessage(content=f"[{name}] Did you finish it?"), HumanMessage(content="Yes.")]
    return history


def _state(current_speaker: str, history: list | None = None) -> dict:
    return {
        "messages": history or [],
        "current_speaker": current_speaker,
        "turn_count": 1,
        "scene_resolved": False,
        "should_end": False,
        "taking_over": False,
    }


def _router_says(monkeypatch, speaker: str) -> None:
    monkeypatch.setattr(
        graph_routing,
        "get_structured_llm",
        lambda purpose, schema: _FakeRoutingLLM(RoutingDecision(speaker=speaker)),
    )


def test_student_addressing_the_other_character_switches_without_taking_over(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    _router_says(monkeypatch, other)

    result = make_routing_node(content, _FixedDraw(3))(_state(current))

    assert result == {"current_speaker": other, "taking_over": False}


def test_student_addressing_the_current_character_wins_over_the_limit(monkeypatch):
    content = _content()
    current = content.role_keys()[0]
    name = content.role(current).name
    _router_says(monkeypatch, current)

    node = make_routing_node(content, _FixedDraw(2))
    result = node(_state(current, _history(name, content.max_consecutive_turns)))

    assert result == {}


def test_nobody_addressed_below_the_drawn_limit_keeps_the_current_character(monkeypatch):
    content = _content()
    current = content.role_keys()[0]
    name = content.role(current).name
    _router_says(monkeypatch, NO_ADDRESSEE)

    result = make_routing_node(content, _FixedDraw(3))(_state(current, _history(name, 2)))

    assert result == {}


def test_nobody_addressed_at_the_drawn_limit_hands_over_and_marks_taking_over(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    name = content.role(current).name
    _router_says(monkeypatch, NO_ADDRESSEE)

    result = make_routing_node(content, _FixedDraw(2))(_state(current, _history(name, 2)))

    assert result == {"current_speaker": other, "taking_over": True}


def test_router_not_configured_still_applies_the_balance(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    name = content.role(current).name

    def _raise(purpose, schema):
        raise ModelNotConfigured("nenhum modelo de roteamento configurado")

    monkeypatch.setattr(graph_routing, "get_structured_llm", _raise)

    node = make_routing_node(content, _FixedDraw(3))
    result = node(_state(current, _history(name, content.max_consecutive_turns)))

    assert result == {"current_speaker": other, "taking_over": True}


def test_router_not_configured_below_the_limit_changes_nothing(monkeypatch):
    content = _content()
    current = content.role_keys()[0]

    def _raise(purpose, schema):
        raise ModelNotConfigured("nenhum modelo de roteamento configurado")

    monkeypatch.setattr(graph_routing, "get_structured_llm", _raise)

    assert make_routing_node(content, _FixedDraw(3))(_state(current)) == {}
