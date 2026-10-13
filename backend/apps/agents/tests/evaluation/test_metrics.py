import pytest

from apps.agents.evaluation.metrics import (
    change_causes,
    introduces_self,
    is_addressed_to_another,
    question_count,
    session_metrics,
    split_rounds,
)
from apps.agents.services.scenario_content import load_scenario_content
from apps.catalog.models import Level, Scenario

pytestmark = pytest.mark.django_db

NAMES = ["Rachel", "Tom"]


@pytest.fixture
def content():
    return load_scenario_content(
        Scenario.objects.get(slug="entrevista-de-emprego"), Level.objects.get(order=3)
    )


def test_rounds_are_the_opening_and_one_per_student_line():
    transcript = [
        "[Rachel] Hi. Ready?",
        "Student: Yes.",
        "[Rachel] Good.",
        "[Tom] Welcome, Rachel. What did you build?",
        "Student: An API.",
    ]

    assert split_rounds(transcript) == [
        ["[Rachel] Hi. Ready?"],
        ["[Rachel] Good.", "[Tom] Welcome, Rachel. What did you build?"],
        [],
    ]


def test_every_question_mark_counts_as_a_question():
    assert question_count(["[Tom] Did you test it? And did it work?", "[Tom] Fine."]) == 2


@pytest.mark.parametrize(
    "line",
    [
        "[Tom] Rachel, do you want to continue?",
        "[Tom] Good question. Rachel, can you answer that one?",
        "[Tom] Rachel? This one is yours.",
    ],
)
def test_a_line_that_calls_the_other_persona_is_dangling(line):
    assert is_addressed_to_another(line, "Tom", NAMES) is True


@pytest.mark.parametrize(
    "line",
    [
        "[Tom] What did you build in your last job?",
        "[Tom] Thanks for sharing that with us today and for the detail about Rachel's team.",
        "[Tom] I work with Rachel every day. Did you use tests?",
    ],
)
def test_a_line_to_the_student_is_not_dangling(line):
    assert is_addressed_to_another(line, "Tom", NAMES) is False


def test_a_persona_never_dangles_to_herself():
    assert is_addressed_to_another("[Tom] Tom, wake up.", "Tom", NAMES) is False


@pytest.mark.parametrize(
    "line",
    ["Hi, I'm Tom, the tech lead.", "I am Tom.", "My name is Tom.", "Hello, this is Tom."],
)
def test_the_ways_of_introducing_oneself(line):
    assert introduces_self(line, "Tom") is True


def test_a_line_without_an_introduction_is_not_one():
    assert introduces_self("Nice work. Which cache did you use?", "Tom") is False


def test_the_causes_of_a_change_come_from_the_events():
    events = [
        {"kind": "addressed", "speaker": "tom", "previous": "rachel"},
        {"kind": "addressed", "speaker": "tom", "previous": "tom"},
        {"kind": "balance_takeover", "leader": "tom", "previous": "rachel", "rounds_led": 3},
        {"kind": "handoff", "origin": "rachel", "target": "tom"},
        {"kind": "handoff_ignored", "speaker": "tom", "reason": "addressed"},
        {"kind": "round_end", "speaker": "tom"},
    ]

    causes = change_causes(events)

    assert causes["student_directed"] == 1
    assert causes["student_same"] == 1
    assert causes["balance_takeover"] == 1
    assert causes["handoff"] == 1
    assert causes["handoff_ignored"] == 1
    assert "round_end" not in causes


def test_the_session_metrics_summarise_the_leaders_and_the_problems(content):
    transcript = [
        "[Rachel] Hi, welcome. Can you tell us about yourself?",
        "Student: I'm a developer.",
        "[Rachel] Nice. What did you build?",
        "Student: An API.",
        "[Rachel] Did you work in a team?",
        "Student: Yes.",
        "[Rachel] Which tests did you write? And how many?",
        "Student: Unit tests.",
        "[Rachel] Great. Tom, can you ask the next one?",
        "Student: Sure.",
        "[Tom] Hi, I'm Tom, the tech lead. Did you use a cache?",
    ]
    events = [{"kind": "balance_takeover", "leader": "tom", "previous": "rachel", "rounds_led": 4}]

    metrics = session_metrics(transcript, events, content)

    assert metrics["leaders"] == ["rachel", "rachel", "rachel", "rachel", "rachel", "tom"]
    assert metrics["changes"] == 1
    assert metrics["max_run"] == 5
    assert metrics["over_limit_runs"] == 1
    assert metrics["multi_question_rounds"] == 1
    assert metrics["dangling_rounds"] == ["[Rachel] Great. Tom, can you ask the next one?"]
    assert metrics["introduced"] == {"Rachel": False, "Tom": True}
    assert metrics["newcomers"] == 1 and metrics["newcomers_introduced"] == 1
    assert metrics["causes"] == {"balance_takeover": 1}
    assert metrics["lines_by_persona"] == {"rachel": 5, "tom": 1}


def test_a_newcomer_who_never_introduces_herself_is_counted(content):
    transcript = [
        "[Rachel] Hello. Ready?",
        "Student: Yes.",
        "[Tom] What did you build?",
    ]

    metrics = session_metrics(transcript, [], content)

    assert metrics["newcomers"] == 1
    assert metrics["newcomers_introduced"] == 0
    assert metrics["introduced"]["Tom"] is False


def test_a_session_where_nobody_new_spoke_has_no_newcomers(content):
    transcript = ["[Rachel] Hello. Ready?", "Student: Yes.", "[Rachel] Good."]

    metrics = session_metrics(transcript, [], content)

    assert metrics["newcomers"] == 0
    assert metrics["max_run"] == 2
