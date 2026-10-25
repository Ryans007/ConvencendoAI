import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import routing as graph_routing
from apps.agents.graph.routing import NO_ADDRESSEE, make_routing_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.schemas import RoutingDecision
from apps.agents.tests.three_roles import PORTER_CUE, hotel_with_porter

pytestmark = pytest.mark.django_db


class _FakeRoutingLLM:
    def __init__(self, decision: RoutingDecision, prompts: list):
        self._decision = decision
        self._prompts = prompts

    def invoke(self, messages):
        self._prompts.append(messages[0].content)
        return self._decision


class _FixedDraw:
    def __init__(self, value: int):
        self.value = value

    def randint(self, low: int, high: int) -> int:
        return self.value


def _director_says(monkeypatch, speaker: str = NO_ADDRESSEE, topic: str = NO_ADDRESSEE) -> list:
    prompts: list = []
    decision = RoutingDecision(speaker=speaker, topic_owner=topic)
    monkeypatch.setattr(
        graph_routing,
        "get_structured_llm",
        lambda purpose, schema: _FakeRoutingLLM(decision, prompts),
    )
    return prompts


def _history(*names: str) -> list:
    history = []
    for name in names:
        history += [AIMessage(content=f"[{name}] How can I help?"), HumanMessage(content="Yes.")]
    return history


def _state(turn: int, history: list, current: str = "emma") -> dict:
    return {
        "messages": history,
        "current_speaker": current,
        "turn_count": turn,
        "scene_resolved": False,
        "should_end": False,
        "hand_floor_to": "",
    }


def _route(content, state: dict, draw: int = 3) -> tuple[dict, list]:
    with collect_round_events() as events:
        result = make_routing_node(content, _FixedDraw(draw))(state)
    return result, events


def test_the_director_knows_the_entry_cue_of_the_supporting_role(monkeypatch):
    prompts = _director_says(monkeypatch)

    _route(hotel_with_porter(max_turns=10), _state(1, _history("Emma")))

    assert f"- Mike (key: mike): carregador de malas. Only this moment: {PORTER_CUE}" in prompts[0]


def test_the_student_calling_the_supporting_role_brings_him_in_first(monkeypatch):
    _director_says(monkeypatch, speaker="mike")

    result, events = _route(hotel_with_porter(max_turns=10), _state(1, _history("Emma")))

    assert result == {"supporting_enters": "first"}
    assert {"kind": "supporting_called", "speaker": "mike", "leader": "emma"} in events


def test_the_subject_of_the_supporting_role_brings_him_in_first(monkeypatch):
    _director_says(monkeypatch, topic="mike")

    result, events = _route(hotel_with_porter(max_turns=10), _state(1, _history("Emma")))

    assert result == {"supporting_enters": "first"}
    assert events[-1]["kind"] == "supporting_topic"


def test_the_rotation_hands_the_floor_to_the_other_principal(monkeypatch):
    _director_says(monkeypatch)
    history = _history("Mike", "Emma", "Emma", "Emma")

    result, _ = _route(hotel_with_porter(max_turns=10), _state(2, history), draw=2)

    assert result == {"hand_floor_to": "james"}


def test_before_half_of_the_scene_nothing_forces_the_supporting_role(monkeypatch):
    _director_says(monkeypatch)

    result, _ = _route(hotel_with_porter(max_turns=10), _state(4, _history("Emma", "James")))

    assert "supporting_enters" not in result


def test_at_half_of_the_scene_the_supporting_role_is_guaranteed(monkeypatch):
    _director_says(monkeypatch)

    result, events = _route(hotel_with_porter(max_turns=10), _state(5, _history("Emma", "James")))

    assert result == {"supporting_enters": "first"}
    guaranteed = {
        "kind": "supporting_guaranteed", "speaker": "mike", "leader": "emma", "mode": "first"
    }
    assert guaranteed in events


def test_calling_a_principal_at_half_of_the_scene_postpones_the_entry(monkeypatch):
    _director_says(monkeypatch, speaker="james")

    result, _ = _route(hotel_with_porter(max_turns=10), _state(5, _history("Emma", "James")))

    assert result == {"current_speaker": "james", "addressed_by_student": True}


def test_the_last_chance_lets_the_called_principal_answer_and_the_supporting_role_close(
    monkeypatch,
):
    _director_says(monkeypatch, speaker="james")

    result, events = _route(hotel_with_porter(max_turns=10), _state(7, _history("Emma", "James")))

    assert result == {
        "current_speaker": "james",
        "addressed_by_student": True,
        "supporting_enters": "after",
    }
    assert events[-1]["mode"] == "after"


def test_the_last_chance_wins_over_a_subject_redirect(monkeypatch):
    _director_says(monkeypatch, speaker="emma", topic="james")

    result, _ = _route(hotel_with_porter(max_turns=10), _state(7, _history("Emma", "James")))

    assert result == {"addressed_by_student": True, "supporting_enters": "after"}


def test_once_the_supporting_role_spoke_nothing_is_forced(monkeypatch):
    _director_says(monkeypatch)
    history = _history("Emma") + [
        AIMessage(content="[Mike] It is next to the lift."),
        AIMessage(content="[Emma] I see. Which floor?"),
        HumanMessage(content="The fifth."),
    ]

    result, _ = _route(hotel_with_porter(max_turns=10), _state(7, history))

    assert "supporting_enters" not in result


def test_with_the_minimum_of_seven_turns_the_window_is_turns_three_and_four(monkeypatch):
    _director_says(monkeypatch)
    content = hotel_with_porter(max_turns=7)

    before, _ = _route(content, _state(2, _history("Emma")))
    at_half, _ = _route(content, _state(3, _history("Emma", "James")))

    assert "supporting_enters" not in before
    assert at_half == {"supporting_enters": "first"}
