import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _Recording:
    def __init__(self, *turns: PersonaTurn):
        self._turns = iter(turns)
        self.prompts: list[str] = []

    def invoke(self, messages):
        self.prompts.append(messages[0].content)
        return next(self._turns)


def _interview():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


def _state(speaker: str, **marks) -> dict:
    history = [
        AIMessage(content="[Rachel] Can you tell me about yourself?"),
        HumanMessage(content="I built a REST API with Django."),
    ]
    return {
        "messages": history,
        "current_speaker": speaker,
        "turn_count": 2,
        "scene_resolved": False,
        "should_end": False,
        **marks,
    }


def _install(monkeypatch, *turns: PersonaTurn) -> _Recording:
    recording = _Recording(*turns)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: recording)
    return recording


def test_a_persona_that_takes_over_and_writes_to_the_colleague_gets_an_answer(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch,
        PersonaTurn(line="Rachel, do you want to continue?", pass_to="student"),
        PersonaTurn(line="Sure. What was the hardest part of that API?", pass_to="student"),
    )

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state("tom", taking_over=True))

    assert [m.content for m in result["messages"]] == [
        "[Tom] Rachel, do you want to continue?",
        "[Rachel] Sure. What was the hardest part of that API?",
    ]
    assert result["current_speaker"] == "rachel"
    assert {"kind": "dangling_answered", "speaker": "tom", "target": "rachel"} in events
    assert "Tom JUST HANDED THIS TO YOU" in recording.prompts[1]


def test_a_persona_called_by_the_student_who_writes_to_the_colleague_gets_an_answer(monkeypatch):
    content = _interview()
    _install(
        monkeypatch,
        PersonaTurn(line="Good question. Rachel, can you answer that one?", pass_to="student"),
        PersonaTurn(line="Yes. How big was the team?", pass_to="student"),
    )

    result = make_persona_node(content, "")(_state("tom", addressed_by_student=True))

    assert len(result["messages"]) == 2
    assert result["messages"][-1].content.startswith("[Rachel] ")
    assert result["current_speaker"] == "rachel"


def test_a_handoff_that_the_second_persona_hands_back_is_answered_by_the_first(monkeypatch):
    content = _interview()
    _install(
        monkeypatch,
        PersonaTurn(line="That one is for Tom.", pass_to="student"),
        PersonaTurn(line="Rachel, you should ask about teamwork first.", pass_to="rachel"),
        PersonaTurn(line="Okay. Did you work in a team on it?", pass_to="student"),
    )

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state("rachel", redirect_to="tom"))

    assert [m.content.split("]")[0] for m in result["messages"]] == ["[Rachel", "[Tom", "[Rachel"]
    assert result["current_speaker"] == "rachel"
    assert {"kind": "dangling_answered", "speaker": "tom", "target": "rachel"} in events


def test_the_guard_adds_at_most_one_line_and_records_when_it_still_dangles(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch,
        PersonaTurn(line="Rachel, do you want to continue?", pass_to="student"),
        PersonaTurn(line="Tom, you go ahead.", pass_to="student"),
    )

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state("tom", taking_over=True))

    assert len(recording.prompts) == 2
    assert len(result["messages"]) == 2
    assert {"kind": "dangling_unresolved", "speaker": "rachel"} in events


def test_a_line_to_the_student_triggers_no_extra_line(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch, PersonaTurn(line="What was the hardest part of that API?", pass_to="student")
    )

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state("tom", taking_over=True))

    assert len(recording.prompts) == 1
    assert len(result["messages"]) == 1
    assert not [e for e in events if e["kind"].startswith("dangling")]


