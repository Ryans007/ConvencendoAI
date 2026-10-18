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
    assert f"{rachel_name} JUST HANDED THIS TO YOU" in second[0].content


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


def _resolving_llm(prompts: list, *turns: PersonaTurn):
    sequence = iter(turns)

    class _SequenceLLM:
        def invoke(self, messages):
            prompts.append(messages[0].content)
            return next(sequence)

    return _SequenceLLM()


def _closing_recorder(monkeypatch, closing: str = "Great, June 30th works.") -> list:
    calls = []

    def fake_closing_line(content, role, history):
        calls.append((role.key, [m.content for m in history]))
        return closing

    monkeypatch.setattr(graph_personas, "generate_closing_line", fake_closing_line)
    return calls


def test_resolved_scene_with_a_question_in_the_line_is_closed_without_it(monkeypatch):
    content = _content()
    rachel = content.role_keys()[0]
    name = content.role(rachel).name
    history = [
        AIMessage(content=f"[{name}] Does the new date work for you?"),
        HumanMessage(content="Yes, it works."),
    ]
    turn = PersonaTurn(
        line="We will set June 30th. Do you need any resources?",
        pass_to="student",
        scene_resolved=True,
    )
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _resolving_llm([], turn)
    )
    calls = _closing_recorder(monkeypatch)

    result = make_persona_node(content, "")(_state(history, rachel))

    assert [m.content for m in result["messages"]] == [f"[{name}] Great, June 30th works."]
    assert result["scene_resolved"] is True
    assert calls == [(rachel, [m.content for m in history])]


def test_resolved_scene_without_a_question_keeps_the_line_and_makes_no_extra_call(monkeypatch):
    content = _content()
    rachel = content.role_keys()[0]
    name = content.role(rachel).name
    turn = PersonaTurn(line="Great, June 30th works. Good luck.", pass_to="student", scene_resolved=True)
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _resolving_llm([], turn)
    )
    calls = _closing_recorder(monkeypatch)

    result = make_persona_node(content, "")(_state([HumanMessage(content="Yes.")], rachel))

    assert [m.content for m in result["messages"]] == [f"[{name}] Great, June 30th works. Good luck."]
    assert calls == []


def test_unresolved_scene_keeps_its_question(monkeypatch):
    content = _content()
    rachel = content.role_keys()[0]
    name = content.role(rachel).name
    turn = PersonaTurn(line="Did you write tests?", pass_to="student", scene_resolved=False)
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _resolving_llm([], turn)
    )
    calls = _closing_recorder(monkeypatch)

    result = make_persona_node(content, "")(_state([HumanMessage(content="Yes.")], rachel))

    assert [m.content for m in result["messages"]] == [f"[{name}] Did you write tests?"]
    assert result["scene_resolved"] is False
    assert calls == []


def test_second_persona_of_a_handoff_resolving_with_a_question_is_the_one_replaced(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    rachel_name, tom_name = content.role(rachel).name, content.role(tom).name
    history = [HumanMessage(content="Yes, it works for me.")]
    first = PersonaTurn(line="Tom, would you like to wrap up?", pass_to=tom)
    second = PersonaTurn(line="Deal. Anything else you need?", pass_to="student", scene_resolved=True)
    sequence_llm = _resolving_llm([], first, second)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: sequence_llm)
    calls = _closing_recorder(monkeypatch, "Deal. We will confirm by email.")
    state = {**_state(history, rachel), "addressed_by_student": True, "redirect_to": tom}

    result = make_persona_node(content, "")(state)

    assert [m.content for m in result["messages"]] == [
        f"[{rachel_name}] Tom, would you like to wrap up?",
        f"[{tom_name}] Deal. We will confirm by email.",
    ]
    assert calls == [(tom, ["Yes, it works for me.", f"[{rachel_name}] Tom, would you like to wrap up?"])]
