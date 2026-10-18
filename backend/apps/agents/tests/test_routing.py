import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import routing as graph_routing
from apps.agents.graph.routing import NO_ADDRESSEE, make_routing_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import RoutingDecision
from apps.catalog.models import Level, Scenario
from apps.llm.services.factory import ModelNotConfigured

pytestmark = pytest.mark.django_db


class _FakeRoutingLLM:
    def __init__(self, decision: RoutingDecision):
        self._decision = decision

    def invoke(self, messages):
        return self._decision


class _FixedDraw:
    def __init__(self, value: int):
        self.value = value

    def randint(self, low: int, high: int) -> int:
        return self.value


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )


def _history(name: str, rounds: int) -> list:
    """Histórico em que `name` conduziu as últimas `rounds` rodadas seguidas."""
    history = []
    for _ in range(rounds):
        history += [AIMessage(content=f"[{name}] Did you finish it?"), HumanMessage(content="Yes.")]
    return history


def _state(current_speaker: str, history: list | None = None) -> dict:
    return {
        "messages": history or [],
        "current_speaker": current_speaker,
        "turn_count": 1,
        "scene_resolved": False,
        "should_end": False,
        "taking_over": False,
    }


def _router_says(monkeypatch, speaker: str) -> None:
    monkeypatch.setattr(
        graph_routing,
        "get_structured_llm",
        lambda purpose, schema: _FakeRoutingLLM(RoutingDecision(speaker=speaker)),
    )


def test_student_addressing_the_other_character_switches_without_taking_over(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    _router_says(monkeypatch, other)

    result = make_routing_node(content, _FixedDraw(3))(_state(current))

    assert result == {
        "current_speaker": other,
        "taking_over": False,
        "addressed_by_student": True,
    }


def test_student_addressing_the_current_character_wins_over_the_limit(monkeypatch):
    content = _content()
    current = content.role_keys()[0]
    name = content.role(current).name
    _router_says(monkeypatch, current)

    node = make_routing_node(content, _FixedDraw(2))
    result = node(_state(current, _history(name, content.max_consecutive_turns)))

    assert result == {"addressed_by_student": True}


def test_nobody_addressed_never_marks_the_student_as_addressing_someone(monkeypatch):
    content = _content()
    current, _ = content.role_keys()
    name = content.role(current).name
    _router_says(monkeypatch, NO_ADDRESSEE)
    node = make_routing_node(content, _FixedDraw(2))

    assert "addressed_by_student" not in node(_state(current, _history(name, 1)))
    assert "addressed_by_student" not in node(_state(current, _history(name, 2)))


def test_nobody_addressed_below_the_drawn_limit_keeps_the_current_character(monkeypatch):
    content = _content()
    current = content.role_keys()[0]
    name = content.role(current).name
    _router_says(monkeypatch, NO_ADDRESSEE)

    result = make_routing_node(content, _FixedDraw(3))(_state(current, _history(name, 2)))

    assert result == {}


def test_nobody_addressed_at_the_drawn_limit_hands_over_and_marks_taking_over(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    name = content.role(current).name
    _router_says(monkeypatch, NO_ADDRESSEE)

    result = make_routing_node(content, _FixedDraw(2))(_state(current, _history(name, 2)))

    assert result == {"current_speaker": other, "taking_over": True}


def test_router_not_configured_still_applies_the_balance(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    name = content.role(current).name

    def _raise(purpose, schema):
        raise ModelNotConfigured("nenhum modelo de roteamento configurado")

    monkeypatch.setattr(graph_routing, "get_structured_llm", _raise)

    node = make_routing_node(content, _FixedDraw(3))
    result = node(_state(current, _history(name, content.max_consecutive_turns)))

    assert result == {"current_speaker": other, "taking_over": True}


def test_router_not_configured_below_the_limit_changes_nothing(monkeypatch):
    content = _content()
    current = content.role_keys()[0]

    def _raise(purpose, schema):
        raise ModelNotConfigured("nenhum modelo de roteamento configurado")

    monkeypatch.setattr(graph_routing, "get_structured_llm", _raise)

    assert make_routing_node(content, _FixedDraw(3))(_state(current)) == {}


class _ReadsTheTranscript:
    """Roteador falso que decide olhando a última fala do aluno na transcrição recebida."""

    def __init__(self, named: dict[str, str]):
        self._named = named
        self.received = []

    def invoke(self, messages):
        self.received.append(messages)
        last_student_line = [
            line for line in messages[1].content.splitlines() if line.startswith("Student:")
        ][-1]
        for name, key in self._named.items():
            if name in last_student_line:
                return RoutingDecision(speaker=key)
        return RoutingDecision(speaker=NO_ADDRESSEE)


def _long_history(content, last_student_line: str) -> list:
    """Conversa longa em que as duas personas se alternam: o equilíbrio de turno não entra."""
    names = [content.role(key).name for key in content.role_keys()]
    history = []
    for index in range(6):
        history += [
            AIMessage(content=f"[{names[index % 2]}] Question {index + 1}?"),
            HumanMessage(content="Yes, I did."),
        ]
    return history[:-1] + [HumanMessage(content=last_student_line)]


def test_router_receives_the_conversation_as_one_text_message(monkeypatch):
    content = _content()
    current = content.role_keys()[0]
    fake = _ReadsTheTranscript({})
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: fake)

    make_routing_node(content, _FixedDraw(3))(_state(current, _long_history(content, "Yes, I did.")))

    assert len(fake.received[0]) == 2
    assert not any(isinstance(message, AIMessage) for message in fake.received[0])


def test_student_calling_the_other_character_in_a_long_conversation_switches(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    other_name = content.role(other).name
    fake = _ReadsTheTranscript({other_name: other})
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: fake)

    history = _long_history(content, f"{other_name}, can I ask you about the stack?")
    result = make_routing_node(content, _FixedDraw(3))(_state(current, history))

    assert result == {
        "current_speaker": other,
        "taking_over": False,
        "addressed_by_student": True,
    }


def test_student_just_answering_in_a_long_conversation_addresses_nobody(monkeypatch):
    content = _content()
    current, other = content.role_keys()
    other_name = content.role(other).name
    fake = _ReadsTheTranscript({other_name: other})
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: fake)

    result = make_routing_node(content, _FixedDraw(3))(
        _state(current, _long_history(content, "Yes, I did."))
    )

    assert result == {}


def test_the_student_talking_to_the_current_character_is_logged_with_the_name(
    monkeypatch, capsys
):
    content = _content()
    current = content.role_keys()[0]
    _router_says(monkeypatch, current)

    make_routing_node(content, _FixedDraw(3))(_state(current, _history(current, 5)))

    logged = capsys.readouterr().out
    assert f"aluno falou com {content.role(current).name}" in logged
    assert "equilibrio de turno nao aplicado" in logged


def test_the_student_turning_to_the_other_character_is_still_logged(monkeypatch, capsys):
    content = _content()
    current, other = content.role_keys()
    _router_says(monkeypatch, other)

    make_routing_node(content, _FixedDraw(3))(_state(current))

    logged = capsys.readouterr().out
    assert f"aluno direcionou para {other} (era {current})" in logged
    assert "aluno falou com" not in logged


def test_nothing_is_logged_for_the_student_when_nobody_is_addressed(monkeypatch, capsys):
    content = _content()
    current = content.role_keys()[0]
    _router_says(monkeypatch, NO_ADDRESSEE)

    make_routing_node(content, _FixedDraw(3))(_state(current))

    logged = capsys.readouterr().out
    assert "aluno falou com" not in logged
    assert "aluno direcionou" not in logged


def test_router_prompt_separates_thanking_by_name_from_calling_someone(monkeypatch):
    content = _content()
    current = content.role_keys()[0]
    fake = _ReadsTheTranscript({})
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: fake)

    history = _long_history(content, "Yes, I did.")
    make_routing_node(content, _FixedDraw(3))(_state(current, history))

    system = fake.received[0][0].content
    assert "A name used only to thank or greet someone" in system
    assert "is also NOT addressing them" in system
    assert "answer with the key of the one who receives" in system
    assert "the student's request or question, never the one who is only being thanked" in system


def _director_says(monkeypatch, speaker: str, topic_owner: str) -> None:
    monkeypatch.setattr(
        graph_routing,
        "get_structured_llm",
        lambda purpose, schema: _FakeRoutingLLM(
            RoutingDecision(speaker=speaker, topic_owner=topic_owner)
        ),
    )


def _interview():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


def test_a_topic_of_the_other_character_hands_them_the_round_without_calling(monkeypatch):
    content = _interview()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, NO_ADDRESSEE, tom)

    with collect_round_events() as events:
        result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result == {"current_speaker": tom, "taking_over": True}
    assert {"kind": "topic_takeover", "speaker": tom, "previous": rachel} in events
    assert {
        "kind": "direction",
        "speaker": NO_ADDRESSEE,
        "topic_owner": tom,
        "leader": rachel,
    } in events


def test_an_ally_does_not_take_the_round_only_because_of_the_topic(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, NO_ADDRESSEE, tom)

    with collect_round_events() as events:
        result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result == {}
    assert not [e for e in events if e["kind"] == "topic_takeover"]
    assert {
        "kind": "direction",
        "speaker": NO_ADDRESSEE,
        "topic_owner": tom,
        "leader": rachel,
    } in events


def test_the_one_who_decides_takes_the_round_when_the_ally_leads_and_the_topic_is_hers(
    monkeypatch,
):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, NO_ADDRESSEE, rachel)

    result = make_routing_node(content, _FixedDraw(3))(_state(tom, _history("Tom", 1)))

    assert result == {"current_speaker": rachel, "taking_over": True}


def test_an_ally_called_by_the_student_still_answers(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, tom, tom)

    result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result["current_speaker"] == tom
    assert result["addressed_by_student"] is True


def test_a_topic_of_the_current_speaker_changes_nothing(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, NO_ADDRESSEE, rachel)

    result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result == {}


def test_a_general_topic_leaves_the_decision_to_the_balance(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, NO_ADDRESSEE, NO_ADDRESSEE)

    result = make_routing_node(content, _FixedDraw(2))(_state(rachel, _history("Rachel", 2)))

    assert result == {"current_speaker": tom, "taking_over": True}


def test_calling_a_persona_for_the_topic_of_the_other_marks_the_redirect(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, rachel, tom)

    with collect_round_events() as events:
        result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result == {"addressed_by_student": True, "redirect_to": tom}
    assert {"kind": "topic_redirect", "speaker": rachel, "target": tom} in events


def test_calling_the_other_persona_for_the_topic_of_a_third_keeps_the_redirect(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, tom, rachel)

    result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result == {
        "current_speaker": tom,
        "taking_over": False,
        "addressed_by_student": True,
        "redirect_to": rachel,
    }


def test_calling_a_persona_for_their_own_topic_marks_no_redirect(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, tom, tom)

    result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert "redirect_to" not in result
    assert result["current_speaker"] == tom


def test_the_topic_of_an_unknown_key_is_ignored(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    _director_says(monkeypatch, NO_ADDRESSEE, "nobody")

    result = make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    assert result == {}


def test_the_director_prompt_carries_who_leads_and_what_each_role_covers(monkeypatch):
    content = _content()
    rachel, tom = content.role_keys()
    fake = _ReadsTheTranscript({})
    monkeypatch.setattr(graph_routing, "get_structured_llm", lambda purpose, schema: fake)

    make_routing_node(content, _FixedDraw(3))(_state(rachel, _history("Rachel", 1)))

    system = fake.received[0][0].content
    assert f"{content.role(rachel).name} is leading now" in system
    assert f"- {content.role(tom).name} (key: {tom}): {content.role(tom).scene_function}" in system
    assert '"topic_owner"' in system
    assert "is the leader's subject" not in system
    assert f"is {content.role(rachel).name}'s subject" in system
