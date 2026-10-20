import csv
import random

import pytest

from apps.agents.evaluation import calibration
from apps.agents.evaluation.case_loader import Target
from apps.agents.evaluation.scorecard import (
    evaluate_targets,
    metric_values,
    role_item_counts,
    situation_check_counts,
)


def _router(routed, accepted, kind, error=""):
    return {
        "id": "R",
        "kind": kind,
        "current": "tom",
        "line": "x",
        "accepted": accepted,
        "routed": routed,
        "correct": None if accepted is None else routed in accepted,
        "error": error,
    }


def _sample(situation, **outcomes):
    return {
        "situation": situation,
        "error": "",
        "expectations": [{"check": c, "ok": ok} for c, ok in outcomes.items()],
        "roles": [],
    }


def _judged(line, **answers):
    items = {
        item: {"answer": answer, "reason": f"{item} {answer}"} for item, answer in answers.items()
    }
    return {"line": line, "items": items, "error": ""}


def test_the_router_metrics_split_named_calls_from_plain_answers():
    router = [
        _router("tom", ["tom"], "named"),
        _router("none", ["tom"], "named"),
        _router("none", ["none", "tom"], "answer"),
        _router("rachel", ["none", "tom"], "answer"),
        _router("none", None, "ambiguous"),
        _router("none", ["tom"], "named", error="falhou"),
    ]

    values = metric_values(router, [], [])

    assert values["router_named_accuracy"] == 0.5
    assert values["router_false_call_rate"] == 0.5


def test_the_situation_rates_count_only_the_samples_that_ran_the_check():
    situations = [
        _sample("a", passes_to=True, single_question=True),
        _sample("a", passes_to=False, single_question=True),
        _sample("b", no_handoff=True),
        {"situation": "c", "error": "quebrou"},
    ]

    counts = situation_check_counts(situations)
    values = metric_values([], situations, [])

    assert counts["passes_to"] == (1, 2)
    assert values["passes_to_rate"] == 0.5
    assert values["single_question_rate"] == 1.0
    assert values["no_handoff_rate"] == 1.0
    assert values["introduces_rate"] is None


def test_the_session_metrics_are_added_up_across_sessions():
    sessions = [
        {"metrics": {"rounds": 10, "dangling_rounds": ["a"], "multi_question_rounds": 1,
                     "over_limit_runs": 1, "newcomers": 1, "newcomers_introduced": 0}},
        {"metrics": {"rounds": 10, "dangling_rounds": [], "multi_question_rounds": 0,
                     "over_limit_runs": 0, "newcomers": 1, "newcomers_introduced": 1}},
        {"error": "quebrou"},
    ]

    values = metric_values([], [], sessions)

    assert values["session_dangling_rounds"] == 1
    assert values["session_multi_question_rate"] == 0.05
    assert values["session_over_limit_runs"] == 1
    assert values["session_intro_rate"] == 0.5


def test_without_sessions_the_session_metrics_have_no_data():
    values = metric_values([], [], [])

    assert values["session_dangling_rounds"] is None
    assert values["role_pass_rate"] is None


def test_the_role_rate_ignores_the_not_applicable_answers():
    sessions = [
        {
            "roles": [
                _judged(
                    "[Tom] a",
                    english_only="yes",
                    no_english_correction="no",
                    only_scene_facts="na",
                )
            ]
        }
    ]
    situations = [{"roles": [_judged("[Tom] b", english_only="yes", no_task_reveal="yes")]}]

    counts = role_item_counts(situations, sessions)
    values = metric_values([], situations, sessions)

    assert counts["english_only"] == {"yes": 2}
    assert counts["only_scene_facts"] == {"na": 1}
    assert values["role_pass_rate"] == pytest.approx(3 / 4)


def test_the_targets_are_compared_by_their_direction():
    targets = [
        Target("a", 0.9, "min", "A"),
        Target("b", 0.1, "max", "B"),
        Target("c", 0.5, "min", "C"),
        Target("d", 0, "max", "D"),
    ]
    values = {"a": 0.95, "b": 0.2, "c": None, "d": 0}

    rows = evaluate_targets(values, targets)

    assert [row["status"] for row in rows] == ["ok", "falhou", "sem dados", "ok"]


def _results():
    situations = [
        {
            "situation": "P1",
            "roles": [
                _judged("[Rachel] one", english_only="yes", no_english_correction="no"),
                _judged("[Tom] two", english_only="yes", only_scene_facts="na"),
            ],
        }
    ]
    sessions = [{"session": "S1", "roles": [_judged("[Tom] three", no_task_reveal="yes")]}]
    return situations, sessions


def test_only_yes_and_no_answers_become_review_items():
    items = calibration.judged_items(*_results())

    assert len(items) == 4
    assert all(item["judge"] in ("yes", "no") for item in items)
    assert {item["source"] for item in items} == {"P1", "S1"}


def test_the_review_file_has_a_blank_human_column(tmp_path):
    items = calibration.judged_items(*_results())
    path = tmp_path / "review.csv"

    written = calibration.write_review_file(items, 3, path, random.Random(1))

    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert written == len(rows) == 3
    assert all(row["human"] == "" for row in rows)
    assert list(rows[0]) == calibration.REVIEW_COLUMNS


def test_the_sample_is_never_larger_than_the_available_items(tmp_path):
    items = calibration.judged_items(*_results())

    assert calibration.write_review_file(items, 50, tmp_path / "r.csv") == 4


def _reviewed(tmp_path, human_answers):
    items = calibration.judged_items(*_results())
    path = tmp_path / "review.csv"
    calibration.write_review_file(items, 4, path, random.Random(2))
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    for row, human in zip(rows, human_answers):
        row["human"] = human
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=calibration.REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path, rows


def test_the_agreement_compares_the_human_with_the_judge(tmp_path):
    path, rows = _reviewed(tmp_path, ["", "", "", ""])
    flipped = [("no" if row["judge"] == "yes" else "yes") for row in rows]
    same = [row["judge"] for row in rows]
    path, rows = _reviewed(tmp_path, [same[0], same[1], same[2], flipped[3]])

    result = calibration.read_agreement(path)

    assert result["reviewed"] == 4
    assert result["agreement"] == pytest.approx(0.75)
    assert len(result["disagreements"]) == 1
    assert result["disagreements"][0]["item"] == rows[3]["item"]


def test_portuguese_answers_and_blanks_are_understood(tmp_path):
    path, rows = _reviewed(tmp_path, ["sim", "não", "", "talvez"])

    result = calibration.read_agreement(path)

    assert result["reviewed"] == 2
    assert result["skipped"] == 2


def test_a_file_nobody_reviewed_has_no_agreement(tmp_path):
    path, _ = _reviewed(tmp_path, ["", "", "", ""])

    assert calibration.read_agreement(path)["agreement"] is None


def test_the_speaker_check_has_its_own_rate():
    situations = [
        {
            "expectations": [
                {"check": "speaker", "ok": True},
            ]
        },
        {
            "expectations": [
                {"check": "speaker", "ok": True},
            ]
        },
    ]

    values = metric_values([], situations, [])

    assert "concedes_rate" not in values
    assert values["speaker_rate"] == 1.0


def test_the_topic_accuracy_is_a_metric_of_its_own():
    router = [
        {"id": "a", "kind": "answer", "correct": True, "error": "", "topic_correct": True},
        {"id": "b", "kind": "answer", "correct": True, "error": "", "topic_correct": False},
        {"id": "c", "kind": "answer", "correct": True, "error": "", "topic_correct": None},
    ]

    values = metric_values(router, [], [])

    assert values["router_topic_accuracy"] == 0.5
