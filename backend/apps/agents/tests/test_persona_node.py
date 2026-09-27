import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _FakeStructuredLLM:
    def __init__(self, turn: PersonaTurn):
        self._turn = turn

    def invoke(self, messages):
        return self._turn


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=1)
    )


def _state(history: list, speaker: str) -> dict:
    return {
        "messages": history,
        "current_speaker": speaker,
        "turn_count": 1,
        "scene_resolved": False,
        "should_end": False,
    }


def test_empty_line_falls_back_to_the_personas_last_question(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    name = content.role(key).name
    history = [
        AIMessage(content=f"[{name}] Welcome. Do you have experience with APIs?"),
        HumanMessage(content="Yes."),
    ]
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _FakeStructuredLLM(PersonaTurn(line="", pass_to="student")),
    )

    result = make_persona_node(content, "")(_state(history, key))

    assert [m.content for m in result["messages"]] == [
        f"[{name}] Let me ask again: Do you have experience with APIs?"
    ]
    assert result["current_speaker"] == key


def test_empty_line_is_retried_once_before_the_fallback(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    name = content.role(key).name
    history = [AIMessage(content=f"[{name}] Do you like Python?"), HumanMessage(content="Yes.")]
    turns = iter([
        PersonaTurn(line="", pass_to="student"),
        PersonaTurn(line="Did you use it at work?", pass_to="student"),
    ])

    class _SequenceLLM:
        def invoke(self, messages):
            return next(turns)

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _SequenceLLM())

    result = make_persona_node(content, "")(_state(history, key))

    assert [m.content for m in result["messages"]] == [f"[{name}] Did you use it at work?"]


def test_empty_line_without_previous_question_uses_a_fixed_closed_line(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    name = content.role(key).name
    history = [AIMessage(content=f"[{name}] Welcome to TechCorp."), HumanMessage(content="Hi.")]
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _FakeStructuredLLM(PersonaTurn(line="", pass_to="student")),
    )

    result = make_persona_node(content, "")(_state(history, key))

    assert len(result["messages"]) == 1
    assert result["messages"][0].content.startswith(f"[{name}] ")
    assert result["messages"][0].content.endswith("?")


def test_empty_line_never_triggers_a_same_round_handoff(monkeypatch):
    content = _content()
    key, other = content.role_keys()
    name = content.role(key).name
    history = [AIMessage(content=f"[{name}] Do you like Python?"), HumanMessage(content="Yes.")]
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _FakeStructuredLLM(PersonaTurn(line="", pass_to=other)),
    )

    result = make_persona_node(content, "")(_state(history, key))

    assert len(result["messages"]) == 1
    assert result["current_speaker"] == key
