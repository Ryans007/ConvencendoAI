from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from apps.agents.services.model_input import conversation_messages


def test_returns_the_instructions_and_a_single_text_message():
    history = [
        AIMessage(content="[Rachel] Did you work in a team?"),
        HumanMessage(content="Yes, I did."),
        AIMessage(content="[Tom] Did you use Python?"),
        HumanMessage(content="No, I didn't."),
    ]

    messages = conversation_messages("You are Tom.", history)

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "You are Tom."
    assert isinstance(messages[1], HumanMessage)


def test_no_persona_line_is_delivered_as_an_assistant_message():
    history = [AIMessage(content="[Rachel] Hi."), HumanMessage(content="Hello.")]

    messages = conversation_messages("prompt", history)

    assert not any(isinstance(message, AIMessage) for message in messages)


def test_transcript_keeps_the_order_and_names_every_author():
    history = [
        AIMessage(content="[Rachel] Did you work in a team?"),
        HumanMessage(content="Yes, I did."),
        AIMessage(content="[Tom] Did you use Python?"),
    ]

    body = conversation_messages("prompt", history)[1].content

    assert body.index("[Rachel] Did you work in a team?") < body.index("Student: Yes, I did.")
    assert body.index("Student: Yes, I did.") < body.index("[Tom] Did you use Python?")
    assert body.startswith("CONVERSATION SO FAR")
    assert body.endswith("Now respond, following your instructions.")


def test_empty_history_still_produces_a_valid_text_message():
    messages = conversation_messages("prompt", [])

    assert len(messages) == 2
    assert "(no one has spoken yet)" in messages[1].content
