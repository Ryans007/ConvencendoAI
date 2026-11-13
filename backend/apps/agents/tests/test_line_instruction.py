import pytest

from apps.agents.services.line_instruction import is_debut, line_instruction
from apps.agents.services.participation import SceneParticipation
from apps.agents.services.scenario_content import load_scenario_content
from apps.agents.tests.three_roles import hotel_with_porter
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db


def _interview():
    content = load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )
    return content.role("rachel"), content.role("tom")


def _spoken(**lines: int) -> SceneParticipation:
    return SceneParticipation(lines_by_role=lines, consecutive_rounds_led=0)


def _flat(text: str) -> str:
    """O texto numa linha só, para comparar frases sem depender de onde o texto quebra."""
    return " ".join(text.split())


def test_the_one_handing_over_talks_about_the_colleague_without_a_question():
    rachel, tom = _interview()

    text = _flat(line_instruction(rachel, _spoken(rachel=2, tom=0), hand_floor_to=tom))

    assert text.startswith("THIS LINE (this overrides every rule above about questions)")
    assert "tell the student, as a statement and in your own words, that Tom continues" in text
    assert "NO question and NO question mark at all" in text
    assert "introducing yourself" not in text


def test_the_one_who_redirects_tells_the_student_who_handles_it_without_a_question():
    rachel, tom = _interview()

    text = _flat(line_instruction(rachel, _spoken(rachel=2, tom=1), redirect_to=tom))

    assert "Tom is the" in text and "right person for that" in text
    assert "Do not answer the subject yourself" in text
    assert "NO question and NO question mark at all" in text


def test_a_newcomer_receiving_the_floor_introduces_themselves_and_does_not_answer_for_the_student():
    rachel, tom = _interview()

    text = _flat(line_instruction(tom, _spoken(rachel=2, tom=0), received_from=rachel))

    assert text.startswith("THIS LINE (this overrides every rule above about how your line starts)")
    assert "Rachel's line was a handover said to the student, not a question for you" in text
    assert "You are Tom, tech lead do time de backend, not the student." in text
    assert "Start your line by introducing yourself" in text
    assert text.index("introducing yourself") < text.index("what the STUDENT said")
    assert "ask the student this turn's question" in text


def test_someone_who_already_spoke_does_not_introduce_themselves_again():
    rachel, tom = _interview()

    text = _flat(line_instruction(tom, _spoken(rachel=3, tom=2), received_from=rachel))

    assert "introducing yourself" not in text
    assert "what the STUDENT said" in text


def test_the_supporting_character_before_the_leader_asks_nothing():
    content = hotel_with_porter()
    emma, mike = content.role("emma"), content.role("mike")

    participation = _spoken(emma=2, james=1, mike=0)

    text = _flat(line_instruction(mike, participation, supporting_first_before=emma))

    assert "NO question and NO question mark at all: Emma asks the student" in text
    assert "introducing yourself" not in text


def test_the_principal_before_the_supporting_character_asks_nothing():
    content = hotel_with_porter()
    james, mike = content.role("james"), content.role("mike")

    text = _flat(line_instruction(james, _spoken(emma=2, james=1, mike=0), supporting_follows=mike))

    assert "NO question and NO question mark at all: Mike speaks right after" in text
    assert "Do not address Mike by name" in text


def test_the_supporting_character_who_closes_asks_one_short_question():
    content = hotel_with_porter()
    james, mike = content.role("james"), content.role("mike")

    participation = _spoken(emma=2, james=2, mike=1)

    text = _flat(line_instruction(mike, participation, supporting_closes_after=james))

    assert "finish with ONE short question to the student" in text
    assert "introducing yourself" not in text


def test_a_newcomer_called_by_the_student_introduces_themselves():
    rachel, tom = _interview()

    text = _flat(line_instruction(tom, _spoken(rachel=2, tom=0)))

    assert "Start your line by introducing yourself" in text
    assert "answer or react briefly to what the student said" in text


def test_an_ordinary_line_has_no_instruction():
    rachel, _ = _interview()

    assert line_instruction(rachel, _spoken(rachel=1, tom=0)) == ""


def test_the_opening_has_no_participation_and_is_not_a_debut():
    rachel, _ = _interview()

    assert not is_debut(rachel, None)
