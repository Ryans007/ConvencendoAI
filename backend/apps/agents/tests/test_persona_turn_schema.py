from apps.agents.services.schemas import PersonaTurn


def test_the_condition_is_decided_before_the_line_is_written():
    fields = list(PersonaTurn.model_fields)

    assert fields.index("condition_met") < fields.index("line")
    assert fields.index("line") < fields.index("scene_resolved")


def test_a_turn_without_the_condition_keeps_a_safe_default():
    turn = PersonaTurn(line="Hello.")

    assert turn.condition_met is False
    assert turn.scene_resolved is False
