import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services.participation import scene_participation
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=1)
    )


def _persona(name: str, text: str = "Hello.") -> AIMessage:
    return AIMessage(content=f"[{name}] {text}")


def _student(text: str = "Yes.") -> HumanMessage:
    return HumanMessage(content=text)


def test_nobody_has_spoken_yet():
    content = _content()
    first = content.role_keys()[0]

    result = scene_participation(content, first, [])

    assert result.lines_by_role == {key: 0 for key in content.role_keys()}
    assert result.consecutive_rounds_led == 0


def test_only_one_persona_has_spoken():
    content = _content()
    first, second = content.role_keys()
    name = content.role(first).name
    history = [
        _persona(name), _student(),
        _persona(name), _student(),
        _persona(name), _student(),
    ]

    result = scene_participation(content, first, history)

    assert result.lines_by_role == {first: 3, second: 0}
    assert result.consecutive_rounds_led == 3


def test_same_round_handoff_counts_as_a_round_led_by_the_last_speaker():
    content = _content()
    first, second = content.role_keys()
    first_name, second_name = content.role(first).name, content.role(second).name
    history = [
        _persona(first_name), _student(),
        _persona(first_name, "Tom, what do you think?"), _persona(second_name), _student(),
    ]

    result_first = scene_participation(content, first, history)
    result_second = scene_participation(content, second, history)

    assert result_first.lines_by_role == {first: 2, second: 1}
    assert result_first.consecutive_rounds_led == 0
    assert result_second.consecutive_rounds_led == 1


def test_normal_alternation_resets_the_streak():
    content = _content()
    first, second = content.role_keys()
    first_name, second_name = content.role(first).name, content.role(second).name
    history = [
        _persona(first_name), _student(),
        _persona(first_name), _student(),
        _persona(second_name), _student(),
        _persona(first_name), _student(),
    ]

    result = scene_participation(content, first, history)

    assert result.lines_by_role == {first: 3, second: 1}
    assert result.consecutive_rounds_led == 1
