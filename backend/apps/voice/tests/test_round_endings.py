import json

import pytest
from asgiref.sync import async_to_sync

from apps.agents.services.schemas import RoutingDecision
from apps.voice import consumers as voice_consumers
from apps.voice.tests.round_shapes import (
    STUDENT_TEXT,
    connect,
    install,
    read_frames,
    speaker,
    student_token,
)
from apps.voice.tests.scene_end import end_after_the_first_turn

pytestmark = pytest.mark.django_db

_OPENING = "Hello, let's talk about the deadline."
_REDIRECT = RoutingDecision(speaker="rachel", topic_owner="tom")
_PASSING = "That one is for Tom."
_RECEIVING = "Sure. What is still missing on the export?"
_CLOSING = "Deal, see you next week."


def test_the_limit_after_a_two_line_round_closes_after_every_line_was_heard(
    django_user_model, monkeypatch
):
    end_after_the_first_turn(monkeypatch, line=_CLOSING, turns=2)
    installed = install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT)
    token = student_token(django_user_model)

    async def run() -> tuple[list, list]:
        communicator = await connect(token)
        await read_frames(communicator, 1)
        await communicator.send_to(bytes_data=b"first-answer")
        first_round = await read_frames(communicator, 2)
        await communicator.send_to(bytes_data=b"second-answer")
        closing = await read_frames(communicator, 1)
        closing.append(json.loads(await communicator.receive_from()))
        closing.append(json.loads(await communicator.receive_from()))
        await communicator.disconnect()
        return first_round, closing

    first_round, closing = async_to_sync(run)()

    assert first_round == [
        speaker("Rachel"),
        ("audio", _PASSING),
        speaker("Tom"),
        ("audio", _RECEIVING),
    ]
    assert closing[:2] == [speaker("Rachel"), ("audio", _CLOSING)]
    assert closing[2] == {"type": "evaluating"}
    assert closing[3]["type"] == "session_ended"
    assert installed.evaluated == [
        [
            f"[Rachel] {_OPENING}",
            STUDENT_TEXT,
            f"[Rachel] {_PASSING}",
            f"[Tom] {_RECEIVING}",
            STUDENT_TEXT,
            f"[Rachel] {_CLOSING}",
        ]
    ]


def test_a_hint_after_a_two_line_round_is_made_from_the_whole_conversation(
    django_user_model, monkeypatch
):
    install(monkeypatch, [_OPENING, _PASSING, _RECEIVING], _REDIRECT)
    seen: list[list[str]] = []

    def suggest(content, history):
        seen.append([message.content for message in history])
        return "Diga o prazo."

    monkeypatch.setattr(voice_consumers, "suggest_answer", suggest)
    token = student_token(django_user_model)

    async def run() -> dict:
        communicator = await connect(token, hints=True)
        await read_frames(communicator, 1)
        await communicator.send_to(bytes_data=b"student-audio")
        await read_frames(communicator, 2)
        await communicator.send_to(text_data=json.dumps({"type": "hint_request"}))
        hint = json.loads(await communicator.receive_from())
        await communicator.disconnect()
        return hint

    assert async_to_sync(run)() == {"type": "hint", "text": "Diga o prazo."}
    assert seen == [
        [
            f"[Rachel] {_OPENING}",
            STUDENT_TEXT,
            f"[Rachel] {_PASSING}",
            f"[Tom] {_RECEIVING}",
        ]
    ]
