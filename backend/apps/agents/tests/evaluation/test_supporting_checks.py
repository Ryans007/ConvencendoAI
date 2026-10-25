import json
import shutil

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.agents.evaluation.case_loader import CASES_DIR, CaseError, Expectation, load_cases
from apps.agents.evaluation.judge import judge_line, judge_round
from apps.agents.evaluation.report import _CHECK_TEXT
from apps.agents.evaluation.schemas import ROLE_ITEMS
from apps.agents.evaluation.situation_layer import check_structural
from apps.agents.tests.evaluation.fakes import JUDGE, FakeModels, role_verdict
from apps.agents.tests.three_roles import hotel_with_porter

pytestmark = pytest.mark.django_db

_CHECKS = ("supporting_not_by_balance", "leader_after_supporting", "max_two_lines")


def _check(name: str, lines: list[str], events: list[dict]) -> bool:
    return check_structural(Expectation(check=name, value=True), lines, events, hotel_with_porter())


def test_the_balance_choosing_the_supporting_role_fails_the_check():
    chose_mike = [{"kind": "balance_takeover", "leader": "mike", "previous": "emma"}]
    chose_james = [{"kind": "balance_takeover", "leader": "james", "previous": "emma"}]

    assert not _check("supporting_not_by_balance", ["[Emma] Hi."], chose_mike)
    assert _check("supporting_not_by_balance", ["[Emma] Hi."], chose_james)


def test_after_the_supporting_role_a_principal_must_lead():
    lines = ["[Mike] It is next to the lift.", "[Emma] Which floor do you prefer?"]

    assert _check("leader_after_supporting", lines, [{"kind": "round_end", "next_speaker": "emma"}])
    assert not _check(
        "leader_after_supporting", lines, [{"kind": "round_end", "next_speaker": "mike"}]
    )
    assert not _check(
        "leader_after_supporting", ["[Emma] Hi."], [{"kind": "round_end", "next_speaker": "emma"}]
    )


def test_a_round_with_three_lines_fails_the_two_lines_check():
    assert _check("max_two_lines", ["[Mike] Yes.", "[Emma] Which floor?"], [])
    assert not _check("max_two_lines", ["[Emma] Mike?", "[Mike] Yes.", "[James] Fine?"], [])


def test_the_new_checks_have_a_report_text():
    assert set(_CHECKS) <= set(_CHECK_TEXT)


def test_a_case_with_a_supporting_check_must_say_true_or_false(tmp_path):
    cases_dir = tmp_path / "cases"
    shutil.copytree(CASES_DIR, cases_dir)
    path = cases_dir / "situations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["situations"][0]["expect"].append({"check": "max_two_lines", "value": "mike"})
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CaseError, match="max_two_lines.*true ou false"):
        load_cases(cases_dir)


def test_the_judge_has_an_item_for_the_supporting_role():
    label, question = ROLE_ITEMS["supporting_stays_brief"]

    assert label == "Coadjuvante não conduz"
    assert "only when the line closes the round" in question
    assert "Use na when the character is not a supporting character" in question


def _capture(monkeypatch) -> list[str]:
    prompts: list[str] = []
    models = FakeModels().install(monkeypatch)

    def judge(messages):
        prompts.append(messages[0].content)
        return role_verdict()

    models.set(JUDGE, "RoleVerdict", judge)
    return prompts


def test_the_judge_knows_the_whole_cast_and_the_presence(monkeypatch):
    prompts = _capture(monkeypatch)
    content = hotel_with_porter()

    judge_line(content, content.role("mike"), [], "[Mike] It is next to the lift.")
    judge_line(content, content.role("emma"), [], "[Emma] James, can you help?")

    assert "Presence in the scene: supporting character" in prompts[0]
    assert "- Emma:" in prompts[0] and "- James:" in prompts[0]
    assert "Presence in the scene: principal character" in prompts[1]
    assert "- Mike: carregador de malas (supporting character)" in prompts[1]
    assert "hand the floor to another one" in prompts[1]


def test_a_line_followed_by_another_in_the_round_is_judged_as_such(monkeypatch):
    prompts = _capture(monkeypatch)
    content = hotel_with_porter()
    history = [AIMessage(content="[Emma] Is the room fine?"), HumanMessage(content="No.")]

    judge_round(
        content, history, ["[Mike] It is next to the lift.", "[Emma] Which floor do you want?"]
    )

    assert "THIS LINE DOES NOT CLOSE THE ROUND" in prompts[0]
    assert "THIS LINE DOES NOT CLOSE THE ROUND" not in prompts[1]
