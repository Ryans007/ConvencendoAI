from dataclasses import replace

import pytest
from langchain_core.messages import HumanMessage

from apps.agents.evaluation.case_loader import load_cases
from apps.agents.evaluation.router_layer import run_router_layer, summarize_router
from apps.agents.evaluation.session_layer import run_session_layer
from apps.agents.evaluation.situation_layer import check_structural, run_situation_layer
from apps.agents.evaluation.case_loader import Expectation
from apps.agents.evaluation.schemas import SemanticVerdict, StudentReply
from apps.agents.services.schemas import ClosingLine, PersonaTurn, RoutingDecision
from apps.agents.tests.evaluation.fakes import JUDGE, PERSONA, ROUTER, FakeModels, role_verdict

pytestmark = pytest.mark.django_db


@pytest.fixture
def loaded(db):
    return load_cases()


def _last_student(messages) -> str:
    """A última fala do aluno, lida do texto único em que o roteador recebe a conversa."""
    body = messages[-1].content
    lines = [line for line in body.splitlines() if line.startswith("Student:")]
    return lines[-1] if lines else ""


def _named_router(messages) -> RoutingDecision:
    """Um roteador ingênuo: quem o aluno menciona primeiro é o chamado, mesmo ao agradecer."""
    text = _last_student(messages)
    mentioned = {key: text.find(key.capitalize()) for key in ("tom", "rachel", "emma", "james")}
    found = {key: position for key, position in mentioned.items() if position >= 0}
    return RoutingDecision(speaker=min(found, key=found.get) if found else "none")


def _router_cases(loaded, *ids):
    return [case for case in loaded.router if case.id in ids]


def test_the_router_layer_counts_hits_and_misses_by_kind(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _named_router)
    cases = _router_cases(loaded, "R01", "R02", "R04", "R13", "R17")

    results = run_router_layer(cases, loaded.contents, repetitions=2)
    summary = summarize_router(results)

    assert len(results) == 10
    assert (summary["named_total"], summary["named_correct"]) == (4, 4)
    assert (summary["answer_total"], summary["answer_wrong"]) == (4, 2)
    assert summary["failed_calls"] == 0


def test_a_router_error_is_listed_with_the_line_the_expected_and_the_obtained(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _named_router)

    results = run_router_layer(_router_cases(loaded, "R04"), loaded.contents, repetitions=1)
    error = summarize_router(results)["errors"][0]

    assert error["line"].startswith("Thanks, Rachel.")
    assert error["accepted"] == ["none", "tom"]
    assert error["routed"] == "rachel"


def test_an_ambiguous_case_is_recorded_but_does_not_count(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", RoutingDecision(speaker="none"))

    summary = summarize_router(
        run_router_layer(_router_cases(loaded, "R13"), loaded.contents, repetitions=1)
    )

    assert len(summary["ambiguous"]) == 1
    assert summary["ambiguous"][0]["routed"] == "none"
    assert summary["named_total"] == 0 and summary["answer_total"] == 0


def test_a_router_that_fails_is_reported_and_not_counted_as_a_miss(loaded, monkeypatch):
    def broken(messages):
        raise RuntimeError("provedor fora do ar")

    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", broken)

    summary = summarize_router(
        run_router_layer(_router_cases(loaded, "R02"), loaded.contents, repetitions=1)
    )

    assert summary["failed_calls"] == 1
    assert summary["named_total"] == 0


def _situation(loaded, situation_id):
    return next(s for s in loaded.situations if s.id == situation_id)


def test_a_situation_round_is_checked_against_what_it_expects(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        PersonaTurn(line="Do you prefer remote or hybrid work?", pass_to="student"),
    )

    results = run_situation_layer(
        [_situation(loaded, "P02-hr-topic-with-hr")],
        loaded.contents,
        samples=1,
        use_judge=False,
    )

    sample = results[0]
    assert sample["round"] == ["[Rachel] Do you prefer remote or hybrid work?"]
    outcomes = {item["check"]: item["ok"] for item in sample["expectations"]}
    assert outcomes == {"no_handoff": True, "single_question": True}


def test_a_persona_that_tries_to_hand_over_alone_is_not_followed(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        PersonaTurn(line="Which query did you improve?", pass_to="tom"),
    )
    situation = replace(
        _situation(loaded, "P01-technical-topic-with-hr"),
        direct=False,
        expectations=[Expectation(check="passes_to", value="tom")],
    )

    results = run_situation_layer([situation], loaded.contents, samples=1, use_judge=False)

    outcomes = {item["check"]: item["ok"] for item in results[0]["expectations"]}
    assert outcomes["passes_to"] is False
    assert len(results[0]["round"]) == 1


def test_a_round_that_ends_dangling_fails_the_check(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        [
            PersonaTurn(line="Tom, this one is yours.", pass_to="tom"),
            PersonaTurn(line="Rachel, you can go on.", pass_to="rachel"),
        ],
    )

    results = run_situation_layer(
        [_situation(loaded, "P01-technical-topic-with-hr")],
        loaded.contents,
        samples=1,
        use_judge=False,
    )

    outcomes = {item["check"]: item["ok"] for item in results[0]["expectations"]}
    assert outcomes["last_line_to_student"] is False
    assert outcomes["introduces"] is False


def test_the_samples_run_the_requested_number_of_times(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(PERSONA, "PersonaTurn", PersonaTurn(line="What is your plan?", pass_to="student"))

    results = run_situation_layer(
        [_situation(loaded, "P02-hr-topic-with-hr")], loaded.contents, samples=3, use_judge=False
    )

    assert [r["sample"] for r in results] == [0, 1, 2]
    assert all(
        item["ok"] for r in results for item in r["expectations"] if item["check"] == "no_handoff"
    )


def test_the_judge_answers_the_semantic_question_and_each_line(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        PersonaTurn(line="We cannot give a discount. Room change?", pass_to="student"),
    )
    models.set(JUDGE, "SemanticVerdict", SemanticVerdict(answer="yes", reason="recusou"))
    models.set(JUDGE, "RoleVerdict", role_verdict(no_english_correction="no"))

    results = run_situation_layer(
        [_situation(loaded, "P12-guest-asks-for-a-discount")],
        loaded.contents,
        samples=1,
        use_judge=True,
    )

    sample = results[0]
    semantic = sample["expectations"][0]
    assert semantic["check"] == "judge" and semantic["ok"] is True
    assert semantic["reason"] == "recusou"
    assert sample["roles"][0]["items"]["no_english_correction"]["answer"] == "no"
    assert sample["roles"][0]["items"]["english_only"]["answer"] == "yes"


def test_a_failing_node_is_recorded_in_the_sample_without_stopping_the_others(loaded, monkeypatch):
    answers = [RuntimeError("quebrou"), PersonaTurn(line="What is your plan?", pass_to="student")]

    def flaky(messages):
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    models = FakeModels().install(monkeypatch)
    models.set(PERSONA, "PersonaTurn", flaky)

    results = run_situation_layer(
        [_situation(loaded, "P02-hr-topic-with-hr")], loaded.contents, samples=2, use_judge=False
    )

    assert "RuntimeError" in results[0]["error"]
    assert results[1]["error"] == ""


def test_a_speaker_expectation_reads_who_said_the_first_line(loaded):
    content = loaded.contents[("negociar-prazo", 3)]
    expects_rachel = Expectation(check="speaker", value="rachel")
    expects_tom = Expectation(check="speaker", value="tom")
    lines = ["[Rachel] The new deadline is next Friday."]

    assert check_structural(expects_rachel, lines, [], content) is True
    assert check_structural(expects_tom, lines, [], content) is False
    assert check_structural(expects_rachel, [], [], content) is False


def test_a_full_session_runs_to_the_end_and_is_measured(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        [
            PersonaTurn(
                line="Hello, I'm Rachel. Ready to talk about the deadline?", pass_to="student"
            ),
            PersonaTurn(
                line="Good, you have a plan. The new deadline is next Friday.",
                pass_to="student",
            ),
        ],
    )
    models.set(ROUTER, "RoutingDecision", RoutingDecision(speaker="none"))
    models.set(JUDGE, "StudentReply", StudentReply(line="Yes, I need one more week."))
    models.set(JUDGE, "RoleVerdict", role_verdict())
    models.set(PERSONA, "ClosingLine", ClosingLine(line="Thank you, bye."))
    profile = next(p for p in loaded.students if p.id == "S2-deadline-negotiation")

    results = run_session_layer([profile], loaded.contents, use_judge=True)

    session = results[0]
    max_turns = loaded.contents[("negociar-prazo", 3)].max_turns
    assert session["error"] == ""
    assert session["turn_count"] == max_turns
    assert session["transcript"][1] == "Student: Yes, I need one more week."
    assert session["metrics"]["rounds"] == max_turns + 1
    assert session["metrics"]["dangling_rounds"] == []
    assert [event["kind"] for event in session["events"]].count("student_turn") == max_turns
    persona_lines = [line for line in session["transcript"] if not line.startswith("Student:")]
    assert len(session["roles"]) == len(persona_lines)
    assert session["roles"][0]["items"]["stays_in_function"]["answer"] == "yes"


def test_a_session_that_fails_is_recorded_without_stopping_the_run(loaded, monkeypatch):
    def broken(messages):
        raise RuntimeError("quebrou")

    models = FakeModels().install(monkeypatch)
    models.set(PERSONA, "PersonaTurn", broken)
    profile = next(p for p in loaded.students if p.id == "S2-deadline-negotiation")

    results = run_session_layer([profile], loaded.contents, use_judge=False)

    assert "RuntimeError" in results[0]["error"]
    assert "transcript" not in results[0]


def _topic_router(owner: str, speaker: str = "none"):
    def decide(messages):
        return RoutingDecision(speaker=speaker, topic_owner=owner)

    return decide


def test_a_situation_through_the_director_hands_the_floor_to_the_owner_of_the_topic(
    loaded, monkeypatch
):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _topic_router("tom"))
    models.set(
        PERSONA,
        "PersonaTurn",
        [
            PersonaTurn(line="Good, thanks. Tom, this one is for you.", pass_to="student"),
            PersonaTurn(
                line="Hi, I'm Tom, the tech lead. Which query did you improve?", pass_to="student"
            ),
        ],
    )

    results = run_situation_layer(
        [_situation(loaded, "P01-technical-topic-with-hr")],
        loaded.contents,
        samples=1,
        use_judge=False,
    )

    outcomes = {item["check"]: item["ok"] for item in results[0]["expectations"]}
    assert results[0]["round"][0].startswith("[Rachel] Good, thanks.")
    assert results[0]["round"][1].startswith("[Tom] Hi, I'm Tom")
    assert outcomes == {
        "speaker": True,
        "passes_to": True,
        "introduces": True,
        "single_question": True,
        "last_line_to_student": True,
    }
    assert {"kind": "topic_takeover", "speaker": "tom", "previous": "rachel"} in results[0]["events"]


def test_a_situation_through_the_director_fails_when_the_topic_stays_with_the_leader(
    loaded, monkeypatch
):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _topic_router("none"))
    models.set(
        PERSONA,
        "PersonaTurn",
        PersonaTurn(line="Which query did you improve?", pass_to="student"),
    )

    results = run_situation_layer(
        [_situation(loaded, "P01-technical-topic-with-hr")],
        loaded.contents,
        samples=1,
        use_judge=False,
    )

    outcomes = {item["check"]: item["ok"] for item in results[0]["expectations"]}
    assert outcomes["passes_to"] is False


def test_a_called_persona_for_the_colleagues_topic_passes_the_round(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _topic_router("tom", speaker="rachel"))
    models.set(
        PERSONA,
        "PersonaTurn",
        [
            PersonaTurn(line="That one is for Tom.", pass_to="student"),
            PersonaTurn(line="Redis can help. Did you try a cache before?", pass_to="student"),
        ],
    )

    results = run_situation_layer(
        [_situation(loaded, "P05-hr-asked-for-technical-opinion")],
        loaded.contents,
        samples=1,
        use_judge=False,
    )

    outcomes = {item["check"]: item["ok"] for item in results[0]["expectations"]}
    assert outcomes["passes_to"] is True
    assert outcomes["last_line_to_student"] is True


def test_the_router_layer_reads_the_owner_of_the_topic_from_the_director(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _topic_router("tom"))

    results = run_router_layer(_router_cases(loaded, "R26", "R27"), loaded.contents, repetitions=1)
    summary = summarize_router(results)

    assert [r["topic_routed"] for r in results] == ["tom", "tom"]
    assert (summary["topic_total"], summary["topic_correct"]) == (2, 1)
    assert summary["topic_errors"][0]["id"] == "R27"
    assert summary["topic_errors"][0]["topic_accepted"] == ["none", "rachel"]


def test_a_call_to_a_persona_for_the_topic_of_the_other_is_the_topic_of_the_other(
    loaded, monkeypatch
):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _topic_router("tom", speaker="rachel"))

    results = run_router_layer(_router_cases(loaded, "R28"), loaded.contents, repetitions=1)

    assert results[0]["routed"] == "rachel"
    assert results[0]["topic_routed"] == "tom"
    assert results[0]["topic_correct"] is True


def test_a_case_without_a_topic_does_not_count_in_the_topic_accuracy(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(ROUTER, "RoutingDecision", _topic_router("none"))

    summary = summarize_router(
        run_router_layer(_router_cases(loaded, "R02"), loaded.contents, repetitions=1)
    )

    assert summary["topic_total"] == 0
