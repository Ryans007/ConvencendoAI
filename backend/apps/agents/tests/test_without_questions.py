from apps.agents.services.personas import without_questions


def test_the_questions_are_dropped_and_the_rest_stays():
    text = "Good answer. Tom, this one is yours. Do you agree?"

    assert without_questions(text) == "Good answer. Tom, this one is yours."


def test_a_line_without_questions_stays_as_it_came():
    assert without_questions("Good answer. Over to you, Tom.") == "Good answer. Over to you, Tom."


def test_a_line_that_is_only_a_question_stays_as_it_came():
    assert without_questions("Which query did you improve?") == "Which query did you improve?"


def test_a_question_in_the_middle_is_dropped():
    assert without_questions("Nice. Why? Tom, go ahead.") == "Nice. Tom, go ahead."
