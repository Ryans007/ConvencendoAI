from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.services.model_input import conversation_messages
from apps.agents.services.transcript import answered_after_hint, transcript_text

_HISTORY = [
    AIMessage(content="[Tom] What decision did you make?"),
    HumanMessage(content="I chose PostgreSQL.", additional_kwargs={"after_hint": True}),
    AIMessage(content="[Rachel] Did you work in a team?"),
    HumanMessage(content="Yes."),
]


def test_marks_are_off_by_default():
    text = transcript_text(_HISTORY)

    assert "Student: I chose PostgreSQL." in text
    assert "suggested answer" not in text


def test_marks_only_the_answers_given_after_a_hint():
    text = transcript_text(_HISTORY, mark_hints=True)

    assert "Student (after a suggested answer): I chose PostgreSQL." in text
    assert "Student: Yes." in text


def test_the_persona_and_the_router_never_see_the_mark():
    body = conversation_messages("prompt", _HISTORY)[1].content

    assert "suggested answer" not in body
    assert "Student: I chose PostgreSQL." in body


def test_answered_after_hint_only_for_flagged_student_turns():
    assert answered_after_hint(_HISTORY[1]) is True
    assert answered_after_hint(_HISTORY[3]) is False
    assert answered_after_hint(AIMessage(content="[Tom] x", additional_kwargs={"after_hint": True})) is False
