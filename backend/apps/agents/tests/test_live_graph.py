import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from apps.agents.graph import personas as graph_personas
from apps.agents.graph.builder import build_scenario_graph
from apps.agents.graph.listen import listen_live
from apps.agents.services.schemas import PersonaTurn
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _FakeStructuredLLM:
    def __init__(self, turn: PersonaTurn):
        self._turn = turn

    def invoke(self, messages):
        return self._turn


def _initial_state():
    return {
        "messages": [],
        "current_speaker": "",
        "turn_count": 0,
        "scene_resolved": False,
        "should_end": False,
    }


def test_live_graph_pauses_at_listen_and_resumes_with_command(monkeypatch):
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    content = load_scenario_content(scenario, level)

    fake_turn = PersonaTurn(
        line="Hello, let's talk about the deadline.", pass_to=None, scene_resolved=False
    )
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _FakeStructuredLLM(fake_turn),
    )

    graph = build_scenario_graph(
        content, memory="", listen_node=listen_live, checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "test-session"}}

    first = graph.invoke(_initial_state(), config=config)

    assert "__interrupt__" in first
    assert first["turn_count"] == 0
    assert len(first["messages"]) == 1  # só a abertura da persona

    second = graph.invoke(Command(resume="I need one more week."), config=config)

    assert "__interrupt__" in second  # ainda não terminou: pausa de novo no próximo listen
    assert second["turn_count"] == 1
    assert len(second["messages"]) == 3  # abertura + turno do aluno + resposta da persona


def test_live_graph_ends_when_student_says_an_exit_word(monkeypatch):
    scenario = Scenario.objects.get(slug="negociar-prazo")
    level = Level.objects.get(order=3)
    content = load_scenario_content(scenario, level)

    fake_turn = PersonaTurn(line="Hello there.", pass_to=None, scene_resolved=False)
    monkeypatch.setattr(
        graph_personas,
        "get_structured_llm",
        lambda purpose, schema: _FakeStructuredLLM(fake_turn),
    )

    graph = build_scenario_graph(
        content, memory="", listen_node=listen_live, checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "test-session-exit"}}

    graph.invoke(_initial_state(), config=config)
    result = graph.invoke(Command(resume="goodbye"), config=config)

    assert "__interrupt__" not in result
