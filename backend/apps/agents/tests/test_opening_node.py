import pytest

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_opening_node
from apps.agents.services.round_trace import collect_round_events
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _Scripted:
    def __init__(self, *lines: str):
        self._lines = iter(lines)
        self.instructions: list[str] = []

    def invoke(self, messages):
        self.instructions.append(messages[1].content)
        return PersonaTurn(line=next(self._lines), pass_to="student")


def _opening(monkeypatch, *lines: str):
    content = load_scenario_content(
        Scenario.objects.get(slug="negociar-prazo"), Level.objects.get(order=3)
    )
    script = _Scripted(*lines)
    monkeypatch.setattr(graph_personas, "get_structured_llm", lambda purpose, schema: script)
    with collect_round_events() as events:
        result = make_opening_node(content, "")({"messages": []})
    return result["messages"][0].content, events, script


def test_an_opening_to_the_student_is_used_as_it_came(monkeypatch):
    line, events, script = _opening(monkeypatch, "Hi, I'm Rachel. What is going on?")

    assert line == "[Rachel] Hi, I'm Rachel. What is going on?"
    assert [event["kind"] for event in events] == ["opening"]
    assert len(script.instructions) == 1


def test_the_opening_instruction_says_to_speak_to_the_student(monkeypatch):
    _, _, script = _opening(monkeypatch, "Hi, I'm Rachel. What is going on?")

    assert "Speak to the student, never to the other character." in script.instructions[0]


def test_an_opening_addressed_to_the_colleague_is_asked_again(monkeypatch):
    line, events, script = _opening(
        monkeypatch,
        "Tom, the client expects the module next week; we need to stay on schedule.",
        "Hi, I'm Rachel. I heard you have an update about the module.",
    )

    assert line == "[Rachel] Hi, I'm Rachel. I heard you have an update about the module."
    assert [event["kind"] for event in events] == ["opening_retried", "opening"]
    assert len(script.instructions) == 2


def test_two_openings_addressed_to_the_colleague_fall_back_to_a_greeting(monkeypatch):
    line, events, _ = _opening(
        monkeypatch,
        "Tom, the client expects the module next week.",
        "Tom, can you start?",
    )

    assert line == "[Rachel] Hello. Let's get started."
    assert [event["kind"] for event in events] == [
        "opening_retried",
        "opening_retried",
        "opening",
    ]
