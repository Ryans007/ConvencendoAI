from apps.agents.services.schemas import PersonaTurn


def test_the_model_has_no_field_to_end_the_scene_or_to_concede():
    assert "scene_resolved" not in PersonaTurn.model_fields
    assert "condition_met" not in PersonaTurn.model_fields


def test_a_turn_keeps_a_safe_default():
    turn = PersonaTurn()

    assert turn.line == ""
    assert turn.pass_to == "student"
