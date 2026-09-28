import dataclasses

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.services.turn_balance import next_leader, should_hand_over
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


class _FixedDraw:
    """Gerador que devolve sempre o mesmo número e guarda o intervalo pedido."""

    def __init__(self, value: int):
        self.value = value
        self.ranges = []

    def randint(self, low: int, high: int) -> int:
        self.ranges.append((low, high))
        return self.value


def test_stays_below_the_drawn_limit():
    assert should_hand_over(2, 3, _FixedDraw(3)) is False


def test_hands_over_at_the_drawn_limit():
    assert should_hand_over(2, 3, _FixedDraw(2)) is True


def test_draws_between_two_and_the_maximum():
    draw = _FixedDraw(3)
    should_hand_over(1, 4, draw)
    assert draw.ranges == [(2, 4)]


def test_maximum_below_two_uses_the_maximum_itself():
    draw = _FixedDraw(1)
    assert should_hand_over(1, 1, draw) is True
    assert draw.ranges == [(1, 1)]


def test_first_round_never_hands_over_with_the_default_maximum():
    assert should_hand_over(1, 3, _FixedDraw(2)) is False


def _content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=1)
    )


def test_next_leader_with_two_characters_is_the_other_one():
    content = _content()
    rachel, tom = content.role_keys()
    assert next_leader(content, rachel, []) == tom


def test_next_leader_with_three_characters_is_who_spoke_longest_ago():
    content = _content()
    rachel_role, tom_role = content.roles
    emma_role = dataclasses.replace(tom_role, key="emma", name="Emma")
    content = dataclasses.replace(content, roles=[rachel_role, tom_role, emma_role])
    history = [
        AIMessage(content="[Emma] Hi."),
        HumanMessage(content="Hi."),
        AIMessage(content="[Tom] Hello."),
        HumanMessage(content="Hello."),
        AIMessage(content="[Rachel] Welcome."),
        HumanMessage(content="Thanks."),
    ]

    assert next_leader(content, "rachel", history) == "emma"
