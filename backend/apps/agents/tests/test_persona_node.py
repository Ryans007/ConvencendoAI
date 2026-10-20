import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.round_trace import collect_round_events
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


def test_persona_handing_the_floor_reacts_and_the_colleague_speaks_right_after(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    rachel_name = content.role(rachel).name
    tom_name = content.role(tom).name
    history = [
        AIMessage(content=f"[{rachel_name}] Did you work in a team on that project?"),
        HumanMessage(content="Yes, I did."),
    ]
    prompts = []
    turns = iter([
        PersonaTurn(line=f"Good to hear that. {tom_name}, it is your turn.", pass_to="student"),
        PersonaTurn(line="Nice. Did you also write the tests?", pass_to="student"),
    ])

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return next(turns)

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())
    state = {**_state(history, rachel), "hand_floor_to": tom}

    with collect_round_events() as events:
        result = make_persona_node(content, "")(state)

    assert f"YOU HAND THE FLOOR TO {tom_name} NOW" in prompts[0]
    assert f"{rachel_name} JUST HANDED THE FLOOR TO YOU" in prompts[1]
    assert [m.content for m in result["messages"]] == [
        f"[{rachel_name}] Good to hear that. {tom_name}, it is your turn.",
        f"[{tom_name}] Nice. Did you also write the tests?",
    ]
    assert result["current_speaker"] == tom
    assert result["hand_floor_to"] == ""
    handoff = next(event for event in events if event["kind"] == "handoff")
    assert handoff["origin"] == rachel
    assert handoff["target"] == tom
    assert handoff["reason"] == "hand_floor"


def test_persona_without_a_handoff_gets_no_handoff_instruction(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    prompts = []

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return PersonaTurn(line="Did you use Python?", pass_to="student")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())

    make_persona_node(content, "")(_state([HumanMessage(content="Hi.")], key))

    assert "HAND THE FLOOR" not in prompts[0]


def test_the_persona_that_hands_the_floor_never_asks_the_student(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    rachel_name = content.role(rachel).name
    tom_name = content.role(tom).name
    history = [
        AIMessage(content=f"[{rachel_name}] Did you work in a team on that project?"),
        HumanMessage(content="Yes, I did."),
    ]
    turns = iter([
        PersonaTurn(
            line=f"Good to hear. {tom_name}, it is your turn. What was the hardest part?",
            pass_to="student",
        ),
        PersonaTurn(line="Nice. Did you also write the tests?", pass_to="student"),
    ])

    class _ScriptedLLM:
        def invoke(self, messages):
            return next(turns)

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _ScriptedLLM())

    with collect_round_events() as events:
        result = make_persona_node(content, "")({**_state(history, rachel), "hand_floor_to": tom})

    assert result["messages"][0].content == (
        f"[{rachel_name}] Good to hear. {tom_name}, it is your turn."
    )
    assert {"kind": "handoff_question_dropped", "speaker": rachel} in events


def test_a_fallback_line_is_never_followed_by_the_handoff(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    rachel_name = content.role(rachel).name
    history = [
        AIMessage(content=f"[{rachel_name}] Did you use Python?"),
        HumanMessage(content="Yes, I did."),
    ]
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _FakeStructuredLLM(PersonaTurn(line="", pass_to="student")),
    )

    result = make_persona_node(content, "")({**_state(history, rachel), "hand_floor_to": tom})

    assert len(result["messages"]) == 1
    assert result["current_speaker"] == rachel


def test_the_persona_prompt_no_longer_asks_the_persona_to_choose_who_speaks_next(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    prompts = []

    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return PersonaTurn(line="Did you use Python?", pass_to="student")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())

    make_persona_node(content, "")(_state([HumanMessage(content="Hi.")], key))

    assert "SHARING THE CONVERSATION" not in prompts[0]
    assert '"pass_to"' not in prompts[0]
    assert "this is your area" not in prompts[0].lower()
    assert "Any question?" not in prompts[0]


def test_persona_receives_the_conversation_as_one_text_message(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    name = content.role(key).name
    history = [
        AIMessage(content=f"[{name}] Did you work in a team?"),
        HumanMessage(content="Yes, I did."),
        AIMessage(content=f"[{name}] Did you use Python?"),
        HumanMessage(content="No, I didn't."),
    ]
    received = []

    class _RecordingLLM:
        def invoke(self, messages):
            received.append(messages)
            return PersonaTurn(line="Did you write tests?", pass_to="student")

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())

    make_persona_node(content, "")(_state(history, key))

    assert len(received[0]) == 2
    assert not any(isinstance(message, AIMessage) for message in received[0])
    assert f"[{name}] Did you use Python?" in received[0][1].content
    assert "Student: No, I didn't." in received[0][1].content


def test_second_persona_of_a_handoff_also_receives_text_with_the_handover_line(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    rachel_name = content.role(rachel).name
    history = [
        AIMessage(content=f"[{rachel_name}] Did you use Python?"),
        HumanMessage(content="Yes, I did."),
    ]
    received = []
    turns = iter([
        PersonaTurn(line="Tom, would you like to take over?", pass_to=tom),
        PersonaTurn(line="Sure. Did you write tests?", pass_to="student"),
    ])

    class _RecordingLLM:
        def invoke(self, messages):
            received.append(messages)
            return next(turns)

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _RecordingLLM())

    state = {**_state(history, rachel), "addressed_by_student": True, "redirect_to": tom}

    make_persona_node(content, "")(state)

    second = received[1]
    assert len(second) == 2
    assert not any(isinstance(message, AIMessage) for message in second)
    assert f"[{rachel_name}] Tom, would you like to take over?" in second[1].content
    assert f"{rachel_name} JUST HANDED THE FLOOR TO YOU" in second[0].content


def _recording_llm(prompts: list, turn: PersonaTurn):
    class _RecordingLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return turn

    return _RecordingLLM()


def test_persona_called_by_the_student_is_told_so_and_closes_the_round(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    history = [
        AIMessage(content=f"[{content.role(rachel).name}] Did you work in a team?"),
        HumanMessage(content="Yes. And Tom, you already use PyTest."),
    ]
    prompts = []
    turn = PersonaTurn(line="Yes, we use PyTest.", pass_to=rachel)
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _recording_llm(prompts, turn)
    )
    state = {**_state(history, tom), "addressed_by_student": True}

    result = make_persona_node(content, "")(state)

    assert "THE STUDENT IS TALKING TO YOU" in prompts[0]
    assert len(prompts) == 1
    assert [m.content for m in result["messages"]] == [
        f"[{content.role(tom).name}] Yes, we use PyTest."
    ]
    assert result["current_speaker"] == tom
    assert result["addressed_by_student"] is False


def test_persona_not_called_by_the_student_gets_no_notice_and_cannot_hand_over_alone(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    history = [HumanMessage(content="Yes, I did.")]
    prompts = []
    turns = iter([
        PersonaTurn(line="Did you write tests?", pass_to=tom),
    ])

    class _SequenceLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return next(turns)

    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: _SequenceLLM())

    result = make_persona_node(content, "")(_state(history, rachel))

    assert "THE STUDENT IS TALKING TO YOU" not in prompts[0]
    assert len(prompts) == 1
    assert [m.content for m in result["messages"]] == [
        f"[{content.role(rachel).name}] Did you write tests?"
    ]
    assert result["current_speaker"] == rachel
    assert result["addressed_by_student"] is False


def test_the_mark_is_cleared_when_the_scene_closes_even_if_the_student_called_someone(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    monkeypatch.setattr(graph_personas, "generate_closing_line", lambda *args: "Thank you.")
    state = {
        **_state([HumanMessage(content="Rachel, thank you.")], key),
        "turn_count": content.max_turns,
        "addressed_by_student": True,
    }

    result = make_persona_node(content, "")(state)

    assert result["addressed_by_student"] is False


def test_the_mark_is_cleared_on_the_closing_hint_turn(monkeypatch):
    content = _content()
    key = content.role_keys()[0]
    monkeypatch.setattr(
        graph_personas,
        "generate_closing_hint_line",
        lambda *args: "Any questions for us?",
    )
    state = {
        **_state([HumanMessage(content="Rachel, thank you.")], key),
        "turn_count": content.max_turns - 2,
        "addressed_by_student": True,
    }

    result = make_persona_node(content, "")(state)

    assert result["addressed_by_student"] is False


def test_a_line_that_grants_what_the_student_wanted_does_not_end_the_scene(monkeypatch):
    content = _content()
    rachel = content.role_keys()[0]
    name = content.role(rachel).name
    turn = PersonaTurn(line="Great, the new date works. What will you do next?", pass_to="student")
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _FakeStructuredLLM(turn)
    )

    with collect_round_events() as events:
        result = make_persona_node(content, "")(_state([HumanMessage(content="Yes.")], rachel))

    assert [m.content for m in result["messages"]] == [
        f"[{name}] Great, the new date works. What will you do next?"
    ]
    assert "scene_resolved" not in result
    assert not [e for e in events if e["kind"] == "concession"]
