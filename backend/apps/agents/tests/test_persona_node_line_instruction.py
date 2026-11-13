import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn
from apps.agents.tests.three_roles import hotel_with_porter
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db

_WHO = re.compile(r"^You are (\w+),")
_END = "Now respond, following your instructions."


class _RecordingLLM:
    """Responde a fala combinada de cada persona e guarda a mensagem final que cada uma recebeu."""

    def __init__(self, lines: dict[str, str], received: dict[str, str]):
        self._lines = lines
        self._received = received

    def invoke(self, messages):
        name = _WHO.match(messages[0].content).group(1)
        self._received[name] = messages[-1].content
        return PersonaTurn(line=self._lines[name], pass_to="student")


def _record(monkeypatch, **lines: str) -> dict[str, str]:
    received: dict[str, str] = {}
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _RecordingLLM(lines, received),
    )
    return received


def _after_conversation(message: str) -> str:
    """O que vem depois de "Now respond, following your instructions.", numa linha só."""
    return " ".join(message.split(_END, 1)[1].split())


def _interview_state(**marks) -> dict:
    history = [
        AIMessage(content="[Rachel] Hi, I'm Rachel from HR. What did you build last year?"),
        HumanMessage(content="I built an API with Redis caching that cut the latency in half."),
    ]
    return {
        "messages": history,
        "current_speaker": "rachel",
        "turn_count": 1,
        "scene_resolved": False,
        "should_end": False,
        "hand_floor_to": "",
        "addressed_by_student": False,
        "redirect_to": "",
        **marks,
    }


def _hotel_state(**marks) -> dict:
    history = [
        AIMessage(content="[Emma] Your new room is ready. Is everything fine?"),
        HumanMessage(content="No, the new room is next to the lift. It is very noisy."),
    ]
    return {
        "messages": history,
        "current_speaker": "emma",
        "turn_count": 3,
        "scene_resolved": False,
        "should_end": False,
        "hand_floor_to": "",
        "addressed_by_student": False,
        "redirect_to": "",
        "supporting_enters": "",
        **marks,
    }


def _interview():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


def test_the_handoff_and_the_debut_each_get_their_line_instruction(monkeypatch):
    received = _record(
        monkeypatch,
        Rachel="Thanks for sharing that. Tom will ask you next.",
        Tom="Hi, I'm Tom, the tech lead. What did you cache first?",
    )

    make_persona_node(_interview(), "")(_interview_state(hand_floor_to="tom"))

    rachel = _after_conversation(received["Rachel"])
    tom = _after_conversation(received["Tom"])
    assert rachel.startswith("THIS LINE (this overrides every rule above about questions)")
    assert "that Tom continues" in rachel
    assert "Rachel's line was a handover said to the student" in tom
    assert "Start your line by introducing yourself" in tom


def test_the_redirect_gets_its_line_instruction(monkeypatch):
    received = _record(
        monkeypatch,
        Rachel="That is a technical choice, Tom is the right person for it.",
        Tom="Hi, I'm Tom, the tech lead. Redis fits that well. How big is your cache?",
    )
    state = _interview_state(addressed_by_student=True, redirect_to="tom")

    make_persona_node(_interview(), "")(state)

    assert "Tom is the right person for that" in _after_conversation(received["Rachel"])


def test_an_ordinary_line_gets_no_line_instruction(monkeypatch):
    received = _record(monkeypatch, Rachel="Great. How did you measure the latency?")
    history = [
        AIMessage(content="[Rachel] Hi, I'm Rachel from HR. What did you build last year?"),
        HumanMessage(content="An API for deliveries."),
        AIMessage(content="[Tom] Hi, I'm Tom. Which database did you use?"),
        HumanMessage(content="PostgreSQL."),
    ]

    make_persona_node(_interview(), "")(_interview_state(messages=history))

    assert received["Rachel"].endswith(_END)


def test_the_supporting_role_first_and_the_leader_after_get_their_instructions(monkeypatch):
    received = _record(
        monkeypatch,
        Mike="Hi, I'm Mike, the porter. Yes, I heard the lift all the time.",
        Emma="I'm sorry about that. Would you like the fifth floor?",
    )

    make_persona_node(hotel_with_porter(max_turns=10), "")(_hotel_state(supporting_enters="first"))

    mike = _after_conversation(received["Mike"])
    assert "NO question and NO question mark at all: Emma asks the student" in mike
    assert "Mike's line was a handover said to the student" in _after_conversation(received["Emma"])


def test_the_principal_before_the_supporting_role_and_the_closing_supporting_role(monkeypatch):
    received = _record(
        monkeypatch,
        James="Of course, the fifth floor is quiet.",
        Mike="Hi, I'm Mike, the porter. I can take your bags up now. Are you ready?",
    )
    state = _hotel_state(
        current_speaker="james", addressed_by_student=True, supporting_enters="after"
    )

    make_persona_node(hotel_with_porter(max_turns=10), "")(state)

    james = _after_conversation(received["James"])
    assert "NO question and NO question mark at all: Mike speaks right after" in james
    assert "finish with ONE short question" in _after_conversation(received["Mike"])
