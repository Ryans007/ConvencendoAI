import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_persona_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.schemas import PersonaTurn
from apps.agents.tests.three_roles import hotel_with_porter

pytestmark = pytest.mark.django_db

_WHO = re.compile(r"^You are (\w+),")


class _ScriptedLLM:
    """Responde com a fala combinada para cada persona e guarda o prompt que cada uma recebeu."""

    def __init__(self, lines: dict[str, str], prompts: dict[str, str]):
        self._lines = lines
        self._prompts = prompts

    def invoke(self, messages):
        system = messages[0].content
        name = _WHO.match(system).group(1)
        self._prompts[name] = system
        return PersonaTurn(line=self._lines[name], pass_to="student")


def _script(monkeypatch, **lines: str) -> dict[str, str]:
    prompts: dict[str, str] = {}
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _ScriptedLLM(lines, prompts),
    )
    return prompts


def _history() -> list:
    return [
        AIMessage(content="[Emma] Your new room is ready. Is everything fine?"),
        HumanMessage(content="No, the new room is next to the lift. It is very noisy."),
    ]


def _state(**flags) -> dict:
    return {
        "messages": _history(),
        "current_speaker": "emma",
        "turn_count": 3,
        "scene_resolved": False,
        "should_end": False,
        "hand_floor_to": "",
        "addressed_by_student": False,
        "redirect_to": "",
        "supporting_enters": "",
        **flags,
    }


def _run(state: dict) -> tuple[dict, list]:
    with collect_round_events() as events:
        result = make_persona_node(hotel_with_porter(max_turns=10), "")(state)
    return result, events


def _lines(result: dict) -> list[str]:
    return [message.content for message in result["messages"]]


def test_first_the_supporting_role_speaks_and_the_leader_asks(monkeypatch):
    prompts = _script(
        monkeypatch,
        Mike="Yes, I heard the lift all the time.",
        Emma="I'm sorry about that. Would you like the fifth floor?",
    )

    result, events = _run(_state(supporting_enters="first"))

    assert _lines(result) == [
        "[Mike] Yes, I heard the lift all the time.",
        "[Emma] I'm sorry about that. Would you like the fifth floor?",
    ]
    assert result["current_speaker"] == "emma"
    assert result["supporting_enters"] == ""
    assert "YOU STEP IN BRIEFLY NOW" in prompts["Mike"]
    assert "Emma speaks right after you" in prompts["Mike"]
    assert "Mike JUST HANDED THE FLOOR TO YOU" in prompts["Emma"]
    assert {"kind": "round_end", "speaker": "emma", "next_speaker": "emma"} in events


def test_after_the_called_principal_answers_and_the_supporting_role_closes(monkeypatch):
    prompts = _script(
        monkeypatch,
        James="Of course, the fifth floor is quiet.",
        Mike="I can take your bags up now. Are you ready?",
    )

    result, events = _run(
        _state(current_speaker="james", addressed_by_student=True, supporting_enters="after")
    )

    assert _lines(result) == [
        "[James] Of course, the fifth floor is quiet.",
        "[Mike] I can take your bags up now. Are you ready?",
    ]
    assert result["current_speaker"] == "james"
    assert "AND Mike JOINS RIGHT AFTER YOU" in prompts["James"]
    assert "THE STUDENT IS TALKING TO YOU\n" not in prompts["James"]
    assert "YOU STEP IN BRIEFLY AND CLOSE THIS TURN" in prompts["Mike"]
    entered = {"kind": "supporting_entered", "speaker": "mike", "mode": "after", "leader": "james"}
    assert entered in events


def test_a_redirect_to_the_supporting_role_keeps_the_principal_leading(monkeypatch):
    _script(
        monkeypatch,
        Emma="Mike carried your bags, he saw the room.",
        Mike="The room is right next to the lift. Do you want a higher floor?",
    )

    result, _ = _run(_state(addressed_by_student=True, redirect_to="mike"))

    assert len(result["messages"]) == 2
    assert result["current_speaker"] == "emma"


def test_a_principal_addressing_the_supporting_role_gets_his_answer_and_keeps_leading(
    monkeypatch,
):
    prompts = _script(
        monkeypatch,
        Emma="Mike, did you hear the lift in that room?",
        Mike="Yes, it was very loud. Do you want me to move your bags?",
    )

    result, events = _run(_state())

    assert len(result["messages"]) == 2
    assert result["current_speaker"] == "emma"
    assert "YOU STEP IN BRIEFLY AND CLOSE THIS TURN" in prompts["Mike"]
    assert "dangling_answered" in [event["kind"] for event in events]


def test_a_round_with_the_supporting_role_never_has_a_third_line(monkeypatch):
    _script(
        monkeypatch,
        Mike="It is right next to the lift.",
        Emma="James, can we give the guest the fifth floor?",
    )

    result, events = _run(_state(supporting_enters="first"))

    assert len(result["messages"]) == 2
    assert {"kind": "dangling_unresolved", "speaker": "emma", "reason": "two_lines"} in events
