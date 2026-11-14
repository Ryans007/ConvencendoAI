import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.personas import make_opening_node, make_persona_node
from apps.agents.graph.state import ScenarioState
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.schemas import PersonaTurn
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _Lines:
    def __init__(self, *lines: str):
        self._lines = iter(lines)

    def invoke(self, messages):
        return PersonaTurn(line=next(self._lines), pass_to="student")


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


def _state(content, **flags) -> dict:
    first = content.role_keys()[0]
    return {
        "messages": [
            AIMessage(content=f"[{content.role(first).name}] Welcome to the interview."),
            HumanMessage(content="I built an API for questions about the law."),
        ],
        "current_speaker": first,
        "turn_count": 1,
        "scene_resolved": False,
        "should_end": False,
        "hand_floor_to": "",
        "addressed_by_student": False,
        "redirect_to": "",
        "supporting_enters": "",
        **flags,
    }


def _graph(node):
    workflow = StateGraph(ScenarioState)
    workflow.add_node("persona", node)
    workflow.add_edge(START, "persona")
    workflow.add_edge("persona", END)
    return workflow.compile(checkpointer=MemorySaver())


def _announced_while_running(node, state: dict) -> tuple[list[dict], list[str]]:
    """O que o nó anunciou durante uma execução em fluxo e as falas que ele devolveu no estado."""

    async def run() -> tuple[list[dict], list[str]]:
        graph = _graph(node)
        config = {"configurable": {"thread_id": "announce"}}
        announced = []
        async for item in graph.astream(state, config=config, stream_mode="custom"):
            announced.append(item)
        snapshot = await graph.aget_state(config)
        return announced, [message.content for message in snapshot.values["messages"]][2:]

    return asyncio.run(run())


def _spoken(announced: list[dict]) -> list[str]:
    return [f"[{item['speaker']}] {item['text']}" for item in announced]


def test_a_round_of_two_lines_announces_each_line_in_the_order_it_is_returned(monkeypatch):
    content = _content()
    first, second = content.role_keys()[:2]
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _Lines("I see. Tom will take it from here.", "Thanks. What is next?"),
    )
    node = make_persona_node(content, "")

    announced, returned = _announced_while_running(node, _state(content, hand_floor_to=second))

    assert len(announced) == 2
    assert _spoken(announced) == returned
    assert announced[0]["speaker"] == content.role(first).name
    assert announced[1]["speaker"] == content.role(second).name


def test_a_round_of_one_line_announces_exactly_that_line(monkeypatch):
    content = _content()
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _Lines("What have you finished so far?"),
    )
    node = make_persona_node(content, "")

    announced, returned = _announced_while_running(node, _state(content))

    assert _spoken(announced) == returned
    assert len(announced) == 1


def test_the_closing_line_is_announced_too(monkeypatch):
    content = _content()
    monkeypatch.setattr(
        graph_personas, "generate_closing_line", lambda content, role, history: "Thank you, goodbye."
    )
    node = make_persona_node(content, "")

    announced, returned = _announced_while_running(
        node, _state(content, turn_count=content.max_turns)
    )

    assert _spoken(announced) == returned
    assert announced[0]["text"] == "Thank you, goodbye."


def test_the_opening_line_is_announced_too(monkeypatch):
    content = _content()
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _Lines("Welcome, let's begin.")
    )
    node = make_opening_node(content, "")

    announced, _ = _announced_while_running(node, {**_state(content), "messages": []})

    assert [item["text"] for item in announced] == ["Welcome, let's begin."]
    assert announced[0]["speaker"] == content.role(content.role_keys()[0]).name


def test_calling_the_node_outside_a_graph_still_works_and_announces_nothing(monkeypatch):
    content = _content()
    monkeypatch.setattr(
        graph_personas, "get_structured_llm", lambda purpose, schema: _Lines("What is next?")
    )
    node = make_persona_node(content, "")

    result = node(_state(content))

    assert [message.content.split("] ", 1)[1] for message in result["messages"]] == ["What is next?"]


def test_a_run_that_does_not_stream_returns_the_same_conversation(monkeypatch):
    content = _content()
    second = content.role_keys()[1]
    state = _state(content, hand_floor_to=second)
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _Lines("I see. Tom will take it from here.", "Thanks. What is next?"),
    )
    plain = _graph(make_persona_node(content, "")).invoke(
        dict(state), config={"configurable": {"thread_id": "plain"}}
    )
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _Lines("I see. Tom will take it from here.", "Thanks. What is next?"),
    )

    _, streamed = _announced_while_running(make_persona_node(content, ""), dict(state))

    assert [message.content for message in plain["messages"]][2:] == streamed
