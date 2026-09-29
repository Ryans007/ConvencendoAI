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


def test_persona_taking_over_gets_the_entering_instruction_and_keeps_the_floor(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    rachel_name = content.role(rachel).name
    history = [
        AIMessage(content=f"[{rachel_name}] Did you work in a team on that project?"),
        HumanMessage(content="Yes, I did."),
    ]
    prompts = []

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return PersonaTurn(line="Nice. Did you also write the tests?", pass_to=rachel)

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())
    state = {**_state(history, tom), "taking_over": True}

    result = make_persona_node(content, "")(state)

    assert "YOU ARE TAKING THE LEAD NOW" in prompts[0]
    assert len(prompts) == 1
    assert result["current_speaker"] == tom
    assert result["taking_over"] is False


def test_persona_not_taking_over_gets_no_entering_instruction(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    prompts = []

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return PersonaTurn(line="Did you use Python?", pass_to="student")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())

    make_persona_node(content, "")(_state([HumanMessage(content="Hi.")], key))

    assert "YOU ARE TAKING THE LEAD NOW" not in prompts[0]


def test_handoff_instruction_has_no_ready_made_line_to_copy(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    prompts = []

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return PersonaTurn(line="Did you use Python?", pass_to="student")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())

    make_persona_node(content, "")(_state([HumanMessage(content="Hi.")], key))

    assert "SHARING THE CONVERSATION" in prompts[0]
    assert "this is your area" not in prompts[0].lower()
    assert "Any question?" not in prompts[0]
