import json
import shutil

import pytest

from apps.agents.evaluation.case_loader import CASES_DIR, CaseError, load_cases

pytestmark = pytest.mark.django_db


@pytest.fixture
def cases_dir(tmp_path):
    """Uma cópia editável dos casos que acompanham o projeto."""
    target = tmp_path / "cases"
    shutil.copytree(CASES_DIR, target)
    return target


def _edit(directory, name, change):
    path = directory / name
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_the_cases_shipped_with_the_project_are_valid():
    loaded = load_cases()

    assert len(loaded.router) == 21
    assert len(loaded.situations) == 15
    assert len(loaded.students) == 5
    assert len(loaded.targets) == 12
    assert ("entrevista-de-emprego", 3) in loaded.contents


def test_a_router_case_knows_its_kind():
    kinds = {case.id: case.kind for case in load_cases().router}

    assert kinds["R02"] == "named"
    assert kinds["R01"] == "answer"
    assert kinds["R13"] == "ambiguous"


def test_named_conversations_are_expanded_into_messages():
    situation = next(s for s in load_cases().situations if s.id == "P01-technical-topic-with-hr")

    assert [type(message).__name__ for message in situation.history] == [
        "AIMessage",
        "HumanMessage",
    ]
    assert situation.history[0].content.startswith("[Rachel] Hi, I'm Rachel")


def test_the_beats_of_a_student_profile_are_numbered():
    profile = next(s for s in load_cases().students if s.id == "S1a-interview-curious")

    assert sorted(profile.beats) == [3, 5, 7, 9]


def test_a_persona_that_is_not_in_the_scenario_stops_the_run_with_the_case(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][0].update(current="tomas"),
    )

    with pytest.raises(CaseError, match=r"P01-technical-topic-with-hr.*'tomas'.*entrevista"):
        load_cases(cases_dir)


def test_a_scenario_that_does_not_exist_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "router.json",
        lambda data: data["cases"][0].update(scenario="cenario-fantasma"),
    )

    with pytest.raises(CaseError, match="R01.*cenario-fantasma"):
        load_cases(cases_dir)


def test_a_level_that_does_not_exist_stops_the_run(cases_dir):
    _edit(cases_dir, "situations.json", lambda data: data["situations"][0].update(level=9))

    with pytest.raises(CaseError, match="nível 9"):
        load_cases(cases_dir)


def test_a_line_without_an_author_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][1].update(history=["hello without author"]),
    )

    with pytest.raises(CaseError, match="P02.*Student:"):
        load_cases(cases_dir)


def test_a_line_by_an_unknown_persona_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][1].update(history=["[Tomás] Hello there."]),
    )

    with pytest.raises(CaseError, match="Tomás.*não é uma persona"):
        load_cases(cases_dir)


def test_an_undefined_named_conversation_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][1].update(history=["@nao-existe"]),
    )

    with pytest.raises(CaseError, match="nao-existe"):
        load_cases(cases_dir)


def test_an_unknown_check_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][1].update(expect=[{"check": "sings", "value": True}]),
    )

    with pytest.raises(CaseError, match="verificação 'sings'"):
        load_cases(cases_dir)


def test_a_flag_check_needs_a_boolean(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][1].update(
            expect=[{"check": "no_handoff", "value": "yes"}]
        ),
    )

    with pytest.raises(CaseError, match="true ou false"):
        load_cases(cases_dir)


def test_a_persona_check_needs_a_persona_of_the_scenario(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][0].update(
            expect=[{"check": "passes_to", "value": "emma"}]
        ),
    )

    with pytest.raises(CaseError, match="'emma' não é uma persona"):
        load_cases(cases_dir)


def test_an_empty_question_for_the_judge_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "situations.json",
        lambda data: data["situations"][1].update(expect=[{"judge": "  "}]),
    )

    with pytest.raises(CaseError, match="pergunta para o juiz está vazia"):
        load_cases(cases_dir)


def test_zero_samples_stop_the_run(cases_dir):
    _edit(cases_dir, "situations.json", lambda data: data["situations"][0].update(samples=0))

    with pytest.raises(CaseError, match="samples"):
        load_cases(cases_dir)


def test_an_accepted_persona_outside_the_scenario_stops_the_run(cases_dir):
    _edit(cases_dir, "router.json", lambda data: data["cases"][0].update(accepted=["emma"]))

    with pytest.raises(CaseError, match="R01.*'emma'"):
        load_cases(cases_dir)


def test_a_beat_that_is_not_a_number_stops_the_run(cases_dir):
    _edit(
        cases_dir,
        "students.json",
        lambda data: data["sessions"][0].update(beats={"third": "do something"}),
    )

    with pytest.raises(CaseError, match="não é um número"):
        load_cases(cases_dir)


def test_a_target_needs_a_direction(cases_dir):
    _edit(
        cases_dir,
        "targets.json",
        lambda data: data["targets"][0].update(direction="around"),
    )

    with pytest.raises(CaseError, match="direction"):
        load_cases(cases_dir)


def test_a_missing_file_is_reported(cases_dir):
    (cases_dir / "router.json").unlink()

    with pytest.raises(CaseError, match="não encontrado"):
        load_cases(cases_dir)


def test_a_file_that_is_not_json_is_reported(cases_dir):
    (cases_dir / "router.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(CaseError, match="não é um JSON válido"):
        load_cases(cases_dir)
