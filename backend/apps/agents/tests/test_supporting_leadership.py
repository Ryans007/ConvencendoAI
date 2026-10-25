import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services.participation import scene_participation
from apps.agents.services.turn_balance import next_leader
from apps.agents.tests.three_roles import PORTER_CUE, hotel_with_porter

pytestmark = pytest.mark.django_db


def _line(name: str, text: str = "Hello.") -> AIMessage:
    return AIMessage(content=f"[{name}] {text}")


def _student(text: str = "Yes.") -> HumanMessage:
    return HumanMessage(content=text)


def test_the_content_knows_the_supporting_role_and_the_principals():
    content = hotel_with_porter()

    assert content.principal_keys() == ["emma", "james"]
    assert content.supporting_role().key == "mike"
    assert content.supporting_role().entry_cue == PORTER_CUE
    assert content.is_supporting("mike") and not content.is_supporting("emma")


def test_the_rotation_never_chooses_the_supporting_role():
    content = hotel_with_porter()
    history = [_line("Mike"), _student(), _line("James"), _student(), _line("Emma"), _student()]

    assert next_leader(content, "emma", history) == "james"


def test_a_round_with_the_supporting_role_still_counts_for_the_principal():
    content = hotel_with_porter()
    history = [
        _line("Emma"), _student(),
        _line("Emma"), _student(),
        _line("Mike", "It is next to the lift."), _line("Emma", "I see. Which floor?"),
        _student(),
    ]

    emma = scene_participation(content, "emma", history)
    mike = scene_participation(content, "mike", history)

    assert emma.consecutive_rounds_led == 3
    assert mike.consecutive_rounds_led == 0
    assert emma.lines_by_role["mike"] == 1


def test_a_round_where_only_the_supporting_role_spoke_keeps_the_previous_leader():
    content = hotel_with_porter()
    history = [
        _line("James"), _student(),
        _line("Mike", "The room is noisy."), _student(),
    ]

    assert scene_participation(content, "james", history).consecutive_rounds_led == 2
    assert scene_participation(content, "mike", history).consecutive_rounds_led == 0
