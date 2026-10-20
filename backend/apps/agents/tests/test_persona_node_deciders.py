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


def _deadline():
    return load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )


def _state(history: list, speaker: str, turn_count: int = 1, **marks) -> dict:
    return {
        "messages": history,
        "current_speaker": speaker,
        "turn_count": turn_count,
        "scene_resolved": False,
        "should_end": False,
        **marks,
    }


def _history() -> list:
    return [
        AIMessage(content="[Rachel] What have you finished so far?"),
        HumanMessage(content="Login and reports. I can deliver the export next Friday."),
    ]


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


def test_the_closing_hint_goes_to_the_decider_the_director_passed_the_floor_to(monkeypatch):
    content = load_scenario_content(
        Scenario.objects.get(slug="problema-no-quarto"), Level.objects.get(order=3)
    )
    spoken = []

    def fake_hint(content_arg, role, history):
        spoken.append(role.key)
        return "I will check that number for you."

    monkeypatch.setattr(graph_personas, "generate_closing_hint_line", fake_hint)

    result = make_persona_node(content, "")(
        _state(
            _history(),
            "emma",
            turn_count=content.max_turns - 2,
            addressed_by_student=True,
            redirect_to="james",
        )
    )

    assert spoken == ["james"]
    assert result["current_speaker"] == "james"
    assert result["messages"][0].content.startswith("[James] ")


def test_the_final_closing_goes_to_the_decider_that_received_the_floor(monkeypatch):
    content = load_scenario_content(
        Scenario.objects.get(slug="problema-no-quarto"), Level.objects.get(order=3)
    )
    spoken = []

    def fake_closing(content_arg, role, history):
        spoken.append(role.key)
        return "Good. We will take care of it."

    monkeypatch.setattr(graph_personas, "generate_closing_line", fake_closing)

    make_persona_node(content, "")(
        _state(_history(), "emma", turn_count=content.max_turns, hand_floor_to="james")
    )

    assert spoken == ["james"]


def test_the_ally_that_received_the_floor_does_not_say_the_closing_hint(monkeypatch):
    content = _deadline()
    spoken = []

    def fake_hint(content_arg, role, history):
        spoken.append(role.key)
        return "The new deadline is next Friday."

    monkeypatch.setattr(graph_personas, "generate_closing_hint_line", fake_hint)

    make_persona_node(content, "")(
        _state(_history(), "rachel", turn_count=content.max_turns - 2, hand_floor_to="tom")
    )

    assert spoken == ["rachel"]
