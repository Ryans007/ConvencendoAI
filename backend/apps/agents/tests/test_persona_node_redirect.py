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
        HumanMessage(content="Rachel, should I use Redis to make the API faster?"),
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


def test_the_called_persona_sends_the_topic_to_the_other_and_the_other_answers(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch,
        PersonaTurn(line="That one is for Tom, he knows it best.", pass_to="student"),
        PersonaTurn(line="Redis can help. Did you try a cache before?", pass_to="student"),
    )
    state = _state("rachel", addressed_by_student=True, redirect_to="tom")

    with collect_round_events() as events:
        result = make_persona_node(content, "")(state)

    assert [m.content for m in result["messages"]] == [
        "[Rachel] That one is for Tom, he knows it best.",
        "[Tom] Redis can help. Did you try a cache before?",
    ]
    assert result["current_speaker"] == "tom"
    assert result["redirect_to"] == ""
    assert result["addressed_by_student"] is False
    assert {"kind": "handoff", "origin": "rachel", "target": "tom"} in events
    assert "THIS SUBJECT IS NOT YOUR AREA" in recording.prompts[0]
    assert "Tom's area in this scene" in recording.prompts[0]
    assert "Rachel JUST HANDED THIS TO YOU" in recording.prompts[1]
    assert "THIS SUBJECT IS NOT YOUR AREA" not in recording.prompts[1]


def test_the_redirect_goes_only_to_the_role_the_director_named(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch,
        PersonaTurn(line="Tom will take that.", pass_to="rachel"),
        PersonaTurn(line="Sure. What did you build?", pass_to="rachel"),
    )

    result = make_persona_node(content, "")(_state("rachel", redirect_to="tom"))

    assert len(recording.prompts) == 2
    assert result["current_speaker"] == "tom"


def test_without_a_redirect_the_persona_speaks_alone_whatever_she_returns(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch, PersonaTurn(line="Any questions about the role?", pass_to="tom")
    )

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state("rachel"))

    assert len(recording.prompts) == 1
    assert len(result["messages"]) == 1
    assert result["current_speaker"] == "rachel"
    assert {"kind": "handoff_ignored", "speaker": "rachel", "reason": "director_decides"} in events


def test_a_redirect_to_the_speaker_herself_is_ignored(monkeypatch):
    content = _interview()
    recording = _install(monkeypatch, PersonaTurn(line="What did you build?", pass_to="student"))

    result = make_persona_node(content, "")(_state("rachel", redirect_to="rachel"))

    assert len(recording.prompts) == 1
    assert "THIS SUBJECT IS NOT YOUR AREA" not in recording.prompts[0]
    assert result["current_speaker"] == "rachel"


def test_a_fallback_line_is_never_followed_by_the_redirected_persona(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch,
        PersonaTurn(line="", pass_to="student"),
        PersonaTurn(line="", pass_to="student"),
    )

    result = make_persona_node(content, "")(_state("rachel", redirect_to="tom"))

    assert len(recording.prompts) == 2
    assert len(result["messages"]) == 1
    assert result["current_speaker"] == "rachel"


def test_the_redirect_is_cleared_when_the_scene_closes(monkeypatch):
    content = _interview()
    monkeypatch.setattr(graph_personas, "generate_closing_line", lambda *args: "Thank you.")
    state = _state("rachel", redirect_to="tom")
    state["turn_count"] = content.max_turns

    result = make_persona_node(content, "")(state)

    assert result["redirect_to"] == ""


def test_the_redirect_is_cleared_on_the_closing_hint_turn(monkeypatch):
    content = _interview()
    monkeypatch.setattr(
        graph_personas, "generate_closing_hint_line", lambda *args: "Any questions for us?"
    )
    state = _state("rachel", redirect_to="tom")
    state["turn_count"] = content.max_turns - 2

    result = make_persona_node(content, "")(state)

    assert result["redirect_to"] == ""


def test_a_scene_resolved_by_the_called_persona_skips_the_redirected_one(monkeypatch):
    content = _interview()
    recording = _install(
        monkeypatch,
        PersonaTurn(line="Good luck with the next steps.", pass_to="student", scene_resolved=True),
    )

    result = make_persona_node(content, "")(_state("rachel", redirect_to="tom"))

    assert len(recording.prompts) == 1
    assert result["scene_resolved"] is True
