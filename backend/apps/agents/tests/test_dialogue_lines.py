from apps.agents.services.dialogue_lines import is_addressed_to_another, speaker_and_text

NAMES = ["Rachel", "Tom"]


def test_a_persona_line_is_split_into_speaker_and_text():
    assert speaker_and_text("[Tom] Hello there.") == ("Tom", "Hello there.")
    assert speaker_and_text("Student: Hello.") is None


def test_a_vocative_at_the_start_is_a_line_addressed_to_the_other_persona():
    assert is_addressed_to_another("[Tom] Rachel, do you want to continue?", "Tom", NAMES) is True
    assert is_addressed_to_another("[Tom] Good point. Rachel, can you answer?", "Tom", NAMES) is True


def test_a_line_to_the_student_is_not_addressed_to_the_other_persona():
    assert is_addressed_to_another("[Tom] What did you build?", "Tom", NAMES) is False
    assert is_addressed_to_another("[Tom] Tom, wake up.", "Tom", NAMES) is False
