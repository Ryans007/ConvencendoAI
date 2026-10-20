import contextvars
import random

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph import routing as graph_routing
from apps.agents.graph.personas import make_opening_node, make_persona_node
from apps.agents.graph.routing import make_routing_node
from apps.agents.services.round_trace import collect_round_events, record_round_event
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn, RoutingDecision
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


@pytest.fixture
def content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


class _Scripted:
    def __init__(self, *turns):
        self._turns = iter(turns)

    def invoke(self, messages):
        return next(self._turns)


def _history():
    return [
        AIMessage(content="[Rachel] Hi, can you tell me about yourself?"),
        HumanMessage(content="I built an API with Django."),
    ]


def test_outside_a_collection_recording_does_nothing():
    record_round_event("round_end", speaker="rachel")


def test_inside_a_collection_events_are_listed_in_order():
    with collect_round_events() as events:
        record_round_event("addressed", speaker="tom")
        record_round_event("round_end", speaker="tom")

    assert [event["kind"] for event in events] == ["addressed", "round_end"]
    assert events[0]["speaker"] == "tom"


def test_events_recorded_in_another_thread_context_reach_the_list():
    with collect_round_events() as events:
        contextvars.copy_context().run(record_round_event, "handoff", origin="rachel")

    assert [event["kind"] for event in events] == ["handoff"]


def test_the_collection_ends_with_the_block():
    with collect_round_events():
        pass

    record_round_event("late")


def _persona_round(monkeypatch, content, turns, state_extra=None):
    script = _Scripted(*turns)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: script)
    node = make_persona_node(content, memory="")
    state = {"messages": _history(), "current_speaker": "rachel", "turn_count": 1}
    state.update(state_extra or {})
    return node(state)


def test_a_handoff_round_records_the_handoff_and_the_end_of_the_round(monkeypatch, content):
    turns = [
        PersonaTurn(line="Tom, this one is yours.", pass_to="tom"),
        PersonaTurn(line="Which part did you build?", pass_to="student"),
    ]

    with collect_round_events() as events:
        _persona_round(monkeypatch, content, turns, {"redirect_to": "tom"})

    kinds = [event["kind"] for event in events]
    assert kinds == ["handoff", "round_end"]
    assert events[0] == {"kind": "handoff", "origin": "rachel", "target": "tom"}
    assert events[1]["speaker"] == "tom" and events[1]["next_speaker"] == "tom"


def test_an_ignored_handoff_is_recorded_with_the_reason(monkeypatch, content):
    turns = [PersonaTurn(line="What did you build?", pass_to="rachel")]

    with collect_round_events() as events:
        _persona_round(monkeypatch, content, turns, {"current_speaker": "tom", "taking_over": True})

    ignored = [event for event in events if event["kind"] == "handoff_ignored"]
    assert ignored == [
        {"kind": "handoff_ignored", "speaker": "tom", "reason": "director_decides"}
    ]


def test_the_opening_is_recorded(monkeypatch, content):
    script = _Scripted(PersonaTurn(line="Hello, welcome.", pass_to="student"))
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: script)

    with collect_round_events() as events:
        make_opening_node(content, "")({"messages": []})

    assert events == [{"kind": "opening", "speaker": "rachel"}]


def test_the_student_choosing_a_persona_is_recorded(monkeypatch, content):
    class _Router:
        def invoke(self, messages):
            return RoutingDecision(speaker="tom")

    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: _Router())
    node = make_routing_node(content, rng=random.Random(1))

    with collect_round_events() as events:
        node({"messages": _history(), "current_speaker": "rachel"})

    assert events == [
        {"kind": "direction", "speaker": "tom", "topic_owner": "none", "leader": "rachel"},
        {"kind": "addressed", "speaker": "tom", "previous": "rachel"},
    ]


def test_the_balance_takeover_is_recorded(monkeypatch, content):
    class _Nobody:
        def invoke(self, messages):
            return RoutingDecision(speaker="none")

    class _Always:
        def randint(self, lower, upper):
            return lower

    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: _Nobody())
    node = make_routing_node(content, rng=_Always())
    history = [
        AIMessage(content="[Rachel] Question one?"),
        HumanMessage(content="Answer one."),
        AIMessage(content="[Rachel] Question two?"),
        HumanMessage(content="Answer two."),
    ]

    with collect_round_events() as events:
        node({"messages": history, "current_speaker": "rachel"})

    assert events == [
        {"kind": "direction", "speaker": "none", "topic_owner": "none", "leader": "rachel"},
        {"kind": "balance_takeover", "leader": "tom", "previous": "rachel", "rounds_led": 2},
    ]


def test_the_round_is_the_same_with_and_without_a_collection(monkeypatch, content):
    def turns():
        return [PersonaTurn(line="What did you build?", pass_to="student")]

    plain = _persona_round(monkeypatch, content, turns())
    with collect_round_events():
        collected = _persona_round(monkeypatch, content, turns())

    assert [m.content for m in plain["messages"]] == [m.content for m in collected["messages"]]
    assert plain["current_speaker"] == collected["current_speaker"]
