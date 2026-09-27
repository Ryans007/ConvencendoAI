from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.graph.edges import make_scene_ended, student_left


def _state(**overrides) -> dict:
    base = {
        "messages": [],
        "current_speaker": "",
        "turn_count": 0,
        "scene_resolved": False,
        "should_end": False,
    }
    return {**base, **overrides}


def test_student_left_ends_when_should_end_flag_is_set():
    assert student_left(_state(should_end=True)) == "end"


def test_student_left_does_not_end_on_words_inside_the_speech():
    for text in ("Okay, goodbye everyone", "Our exit strategy was clear", "I quit that job"):
        state = _state(messages=[HumanMessage(content=text)])
        assert student_left(state) == "continue"


def test_student_left_continues_otherwise():
    state = _state(messages=[HumanMessage(content="Nice to meet you")])
    assert student_left(state) == "continue"


def test_scene_ended_when_scene_resolved():
    scene_ended = make_scene_ended(max_turns=10)
    assert scene_ended(_state(scene_resolved=True)) == "end"


def test_scene_ended_when_turn_limit_reached():
    scene_ended = make_scene_ended(max_turns=3)
    assert scene_ended(_state(turn_count=3)) == "end"


def test_scene_ended_continues_below_limit():
    scene_ended = make_scene_ended(max_turns=3)
    state = _state(turn_count=1, messages=[AIMessage(content="[Rachel] Hello")])
    assert scene_ended(state) == "continue"
