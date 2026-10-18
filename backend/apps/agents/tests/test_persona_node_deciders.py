import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn
from apps.catalog.models import Level, Scenario, ScenarioRole

pytestmark = pytest.mark.django_db


class _Scripted:
    def __init__(self, *turns: PersonaTurn):
        self._turns = iter(turns)

    def invoke(self, messages):
        return next(self._turns)


def _install(monkeypatch, *turns: PersonaTurn) -> None:
    scripted = _Scripted(*turns)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: scripted)


def _resolving(line: str) -> PersonaTurn:
    return PersonaTurn(line=line, pass_to="student", scene_resolved=True)


def _deadline():
    return load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )


def _state(history: list, speaker: str, turn_count: int = 1) -> dict:
    return {
        "messages": history,
        "current_speaker": speaker,
        "turn_count": turn_count,
        "scene_resolved": False,
        "should_end": False,
    }


def _history() -> list:
    return [
        AIMessage(content="[Rachel] What have you finished so far?"),
        HumanMessage(content="Login and reports. I can deliver the export next Friday."),
    ]


def test_an_ally_marking_the_scene_as_resolved_is_ignored_and_recorded(monkeypatch):
    content = _deadline()
    _install(monkeypatch, _resolving("Okay, the deadline is next Friday."))

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state(_history(), "tom"))

    assert result["scene_resolved"] is False
    assert {"kind": "resolution_ignored", "speaker": "tom"} in events
    assert [e for e in events if e["kind"] == "round_end"][0]["scene_resolved"] is False


def test_the_pm_marking_the_scene_as_resolved_closes_it(monkeypatch):
    content = _deadline()
    _install(monkeypatch, _resolving("Fine. The new deadline is next Friday."))

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state(_history(), "rachel"))

    assert result["scene_resolved"] is True
    assert not [e for e in events if e["kind"] == "resolution_ignored"]


def test_the_second_speaker_of_a_handoff_is_held_to_the_same_rule(monkeypatch):
    content = _deadline()
    first = PersonaTurn(line="Tom, what do you think?", pass_to="tom")
    _install(monkeypatch, first, _resolving("Sure, next Friday works."))

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state(_history(), "rachel"))

    assert result["scene_resolved"] is False
    assert {"kind": "resolution_ignored", "speaker": "tom"} in events


def test_the_closing_hint_on_the_allys_turn_is_said_by_the_pm(monkeypatch):
    content = _deadline()
    spoken = []

    def fake_hint(content_arg, role, history):
        spoken.append(role.key)
        return "The new deadline is next Friday. Is that clear?"

    monkeypatch.setattr(graph_personas, "generate_closing_hint_line", fake_hint)

    result = make_persona_node(content, "")(
        _state(_history(), "tom", turn_count=content.max_turns - 2)
    )

    assert spoken == ["rachel"]
    assert result["current_speaker"] == "rachel"
    assert result["messages"][0].content.startswith("[Rachel] ")


def test_the_final_closing_on_the_allys_turn_is_said_by_the_pm(monkeypatch):
    content = _deadline()
    spoken = []

    def fake_closing(content_arg, role, history):
        spoken.append(role.key)
        return "Good. The new deadline is next Friday."

    monkeypatch.setattr(graph_personas, "generate_closing_line", fake_closing)

    with collect_round_events() as events:
        result = make_persona_node(content, "")(
            _state(_history(), "tom", turn_count=content.max_turns)
        )

    assert spoken == ["rachel"]
    assert result["current_speaker"] == "rachel"
    assert result["scene_resolved"] is True
    assert {"kind": "closing", "speaker": "rachel"} in events


def test_the_closing_hint_on_the_deciders_turn_stays_with_the_decider(monkeypatch):
    content = load_scenario_content(
        Scenario.objects.get(slug="problema-no-quarto"), Level.objects.get(order=3)
    )
    spoken = []

    def fake_hint(content_arg, role, history):
        spoken.append(role.key)
        return "I will send a technician now."

    monkeypatch.setattr(graph_personas, "generate_closing_hint_line", fake_hint)

    result = make_persona_node(content, "")(
        _state(_history(), "emma", turn_count=content.max_turns - 2)
    )

    assert spoken == ["emma"]
    assert result["current_speaker"] == "emma"


def test_a_scenario_without_any_mark_lets_the_ally_resolve_the_scene(monkeypatch):
    ScenarioRole.objects.filter(scenario__slug="negociar-prazo").update(decides_outcome=False)
    content = _deadline()
    _install(monkeypatch, _resolving("Okay, next Friday."))

    result = make_persona_node(content, "")(_state(_history(), "tom"))

    assert result["scene_resolved"] is True
