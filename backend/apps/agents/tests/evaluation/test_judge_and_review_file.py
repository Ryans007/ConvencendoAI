import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.agents.evaluation import calibration
from apps.agents.evaluation.case_loader import load_cases
from apps.agents.evaluation.judge import CONTEXT_LINES, context_lines, judge_line
from apps.agents.evaluation.schemas import ROLE_ITEMS, StudentReply
from apps.agents.evaluation.session_layer import run_session_layer
from apps.agents.evaluation.situation_layer import run_situation_layer
from apps.agents.services.schemas import ClosingLine, PersonaTurn, RoutingDecision
from apps.agents.tests.evaluation.fakes import JUDGE, PERSONA, ROUTER, FakeModels, role_verdict
from langchain_core.messages import AIMessage, HumanMessage

pytestmark = pytest.mark.django_db

CLOSING_MARK = "THIS IS THE FINAL LINE OF THE SCENE"


@pytest.fixture
def loaded(db):
    return load_cases()


def _capturing_judge(models: FakeModels, prompts: list[str]) -> None:
    def judge(messages):
        prompts.append(messages[0].content)
        return role_verdict()

    models.set(JUDGE, "RoleVerdict", judge)


def _role(loaded, scenario="entrevista-de-emprego", level=3, key="rachel"):
    content = loaded.contents[(scenario, level)]
    return content, content.role(key)


def test_the_judge_receives_the_conversation_before_the_line(loaded, monkeypatch):
    prompts: list[str] = []
    models = FakeModels().install(monkeypatch)
    _capturing_judge(models, prompts)
    content, role = _role(loaded)
    history = [
        AIMessage(content="[Rachel] Tell me about your work."),
        HumanMessage(content="I handle two million requests a day."),
    ]

    judge_line(content, role, history, "[Rachel] Great, 2 million requests is impressive.")

    assert "I handle two million requests a day." in prompts[0]
    assert CLOSING_MARK not in prompts[0]


def test_the_scene_facts_item_accepts_what_the_student_already_said():
    description = ROLE_ITEMS["only_scene_facts"][1]

    assert "already said by the student" in description
    assert "is not invented" in description


def test_a_final_line_is_judged_as_a_closing(loaded, monkeypatch):
    prompts: list[str] = []
    models = FakeModels().install(monkeypatch)
    _capturing_judge(models, prompts)
    content, role = _role(loaded, key="tom")

    judge_line(content, role, [], "[Tom] Thanks for the chat, see you next week.", final=True)

    assert CLOSING_MARK in prompts[0]
    assert "NO question to" in prompts[0]


def test_the_context_keeps_only_the_last_lines():
    history = [HumanMessage(content=f"line {n}") for n in range(10)]

    assert context_lines(history) == [f"Student: line {n}" for n in range(10 - CONTEXT_LINES, 10)]
    assert len(context_lines(history, limit=None)) == 10


def _fake_session(monkeypatch, prompts):
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        [
            PersonaTurn(line="Hello, I'm Rachel. Ready?", pass_to="student"),
            PersonaTurn(line="What is your plan?", pass_to="student"),
            PersonaTurn(
                line="Good. The new deadline is next Friday.",
                pass_to="student",
                scene_resolved=True,
            ),
        ],
    )
    models.set(PERSONA, "ClosingLine", ClosingLine(line="Thank you, bye."))
    models.set(ROUTER, "RoutingDecision", RoutingDecision(speaker="rachel"))
    models.set(JUDGE, "StudentReply", StudentReply(line="I need one more week."))
    _capturing_judge(models, prompts)


def test_only_the_last_persona_line_of_a_session_is_judged_as_the_closing(loaded, monkeypatch):
    prompts: list[str] = []
    _fake_session(monkeypatch, prompts)
    profile = next(p for p in loaded.students if p.id == "S2-deadline-negotiation")

    session = run_session_layer([profile], loaded.contents, use_judge=True)[0]

    flags = [judged["final"] for judged in session["roles"]]
    assert flags == [False, False, True]
    assert [CLOSING_MARK in prompt for prompt in prompts] == flags


def test_each_judged_line_keeps_the_context_the_judge_saw(loaded, monkeypatch):
    prompts: list[str] = []
    _fake_session(monkeypatch, prompts)
    profile = next(p for p in loaded.students if p.id == "S2-deadline-negotiation")

    session = run_session_layer([profile], loaded.contents, use_judge=True)[0]

    assert session["roles"][0]["context"] == []
    assert session["roles"][2]["context"] == session["transcript"][:4]
    assert all(len(judged["context"]) <= CONTEXT_LINES for judged in session["roles"])


def test_a_situation_sample_keeps_its_history_and_the_context_of_each_line(loaded, monkeypatch):
    models = FakeModels().install(monkeypatch)
    models.set(PERSONA, "PersonaTurn", PersonaTurn(line="What is your plan?", pass_to="student"))
    _capturing_judge(models, [])
    situation = next(s for s in loaded.situations if s.id == "P02-hr-topic-with-hr")

    sample = run_situation_layer([situation], loaded.contents, samples=1, use_judge=True)[0]

    assert len(sample["context"]) == 2
    assert sample["roles"][0]["context"] == sample["context"]
    assert sample["roles"][0]["final"] is False


def _judged(line, context, answer="no"):
    return {
        "line": line,
        "context": context,
        "final": False,
        "items": {"only_scene_facts": {"answer": answer, "reason": "motivo"}},
        "error": "",
    }


def test_the_review_items_carry_the_context_in_one_cell():
    sessions = [{"session": "S1", "roles": [_judged("[Rachel] Nice.", ["a", "b"])]}]

    item = calibration.judged_items([], sessions)[0]

    assert item["context"] == "a | b"


def test_the_review_file_has_the_context_column_next_to_the_line(tmp_path):
    sessions = [{"session": "S1", "roles": [_judged("[Rachel] Nice.", ["a", "b"])]}]
    path = tmp_path / "review.csv"

    calibration.write_review_file(calibration.judged_items([], sessions), 1, path)

    rows = calibration.read_rows(path)
    assert list(rows[0]) == calibration.REVIEW_COLUMNS
    assert rows[0]["context"] == "a | b" and rows[0]["human"] == ""


PADDED_FILE = (
    "id, source              , context        , line                        , item           , "
    "item_label   , judge, reason                      , human\n"
    ' 1, P01-technical      , "a, b"         , "[Tom] Great, nice one."    , only_scene_facts, '
    'Só usa fatos  , no   , "Cita número, sem fonte."   , yes\n'
    " 2, S1b-interview-shy  ,                , [Tom] Thanks.               , english_only    , "
    "Só inglês     , yes  , Em inglês.                  , yes  \n"
)


def test_a_file_saved_with_aligned_columns_and_quoted_commas_is_read_correctly(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(PADDED_FILE, encoding="utf-8-sig")

    rows = calibration.read_rows(path)

    assert len(rows) == 2
    assert rows[0]["context"] == "a, b"
    assert rows[0]["line"] == "[Tom] Great, nice one."
    assert rows[0]["reason"] == "Cita número, sem fonte."
    assert rows[0]["human"] == "yes"
    assert rows[1]["context"] == "" and rows[1]["human"] == "yes"


def test_the_agreement_works_on_the_aligned_file(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(PADDED_FILE, encoding="utf-8-sig")

    result = calibration.read_agreement(path)

    assert result["reviewed"] == 2
    assert result["agreement"] == 0.5
    assert result["disagreements"][0]["line"] == "[Tom] Great, nice one."


def test_blank_lines_in_the_file_are_ignored(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(PADDED_FILE + "\n\n", encoding="utf-8-sig")

    assert len(calibration.read_rows(path)) == 2


FINAL_TOM_LINE = "[Tom] See you next week. Thanks for the chat."


def _old_results(loaded):
    situation = next(s for s in loaded.situations if s.id == "P01-technical-topic-with-hr")
    first = "[Rachel] Great, 2 million requests is impressive. What change sped up the queries?"
    return {
        "situations": [
            {
                "situation": situation.id,
                "round": [first],
                "roles": [{"line": first, "items": {}, "error": ""}],
            }
        ],
        "sessions": [
            {
                "session": "S1b-interview-shy",
                "transcript": [
                    "[Rachel] Hi, I'm Rachel.",
                    "Student: Hello.",
                    "[Tom] Welcome.",
                    "Student: Thanks.",
                    FINAL_TOM_LINE,
                ],
                "roles": [
                    {"line": FINAL_TOM_LINE, "items": {}, "error": ""}
                ],
            }
        ],
    }


def _filled_file(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(
        "id, source                       , line                         , item     , "
        "item_label , judge, reason , human\n"
        '27, P01-technical-topic-with-hr  , "[Rachel] Great, 2 million requests is impressive. '
        'What change sped up the queries?", only_scene_facts, Fatos     , no   , motivo , yes\n'
        '40, S1b-interview-shy            , "[Tom] See you next week. Thanks for the chat."'
        "        , acts_as_archetype, Arquétipo, no   , motivo , yes\n"
        "41, S9-unknown                   , [Tom] Not in the results     , english_only    , "
        "Inglês     , yes  , motivo , \n",
        encoding="utf-8-sig",
    )
    return path


def test_the_context_is_added_to_a_file_that_was_already_filled(loaded, tmp_path):
    path = _filled_file(tmp_path)
    results = tmp_path / "results.json"
    results.write_text(json.dumps(_old_results(loaded)), encoding="utf-8")

    done = calibration.add_context(path, results, loaded)

    rows = calibration.read_rows(path)
    assert done == {"found": 2, "missing": 1}
    assert rows[0]["context"].startswith("[Rachel] Hi, I'm Rachel from HR.")
    assert rows[0]["context"].endswith("made the database queries much faster.")
    assert rows[1]["context"] == (
        "[Rachel] Hi, I'm Rachel. | Student: Hello. | [Tom] Welcome. | Student: Thanks."
    )
    assert rows[2]["context"] == ""


def test_the_answers_survive_the_addition_of_the_context(loaded, tmp_path):
    path = _filled_file(tmp_path)
    results = tmp_path / "results.json"
    results.write_text(json.dumps(_old_results(loaded)), encoding="utf-8")

    calibration.add_context(path, results, loaded)

    rows = calibration.read_rows(path)
    assert [row["human"] for row in rows] == ["yes", "yes", ""]
    assert [row["id"] for row in rows] == ["27", "40", "41"]
    assert rows[0]["line"].startswith("[Rachel] Great, 2 million requests")


def test_a_copy_of_the_original_file_is_kept(loaded, tmp_path):
    path = _filled_file(tmp_path)
    original = path.read_text(encoding="utf-8-sig")
    results = tmp_path / "results.json"
    results.write_text(json.dumps(_old_results(loaded)), encoding="utf-8")

    calibration.add_context(path, results, loaded)

    assert (tmp_path / "review.csv.bak").read_text(encoding="utf-8-sig") == original


def test_the_stored_context_wins_over_the_rebuilt_one(loaded, tmp_path):
    path = _filled_file(tmp_path)
    data = _old_results(loaded)
    data["sessions"][0]["roles"][0]["context"] = ["guardado"]
    results = tmp_path / "results.json"
    results.write_text(json.dumps(data), encoding="utf-8")

    calibration.add_context(path, results, loaded)

    assert calibration.read_rows(path)[1]["context"] == "guardado"


def _command(*args):
    from io import StringIO

    out = StringIO()
    call_command("evaluate_conversation", *args, stdout=out)
    return out.getvalue()


def test_the_command_adds_the_context_to_a_filled_file(loaded, tmp_path):
    path = _filled_file(tmp_path)
    (tmp_path / "results.json").write_text(json.dumps(_old_results(loaded)), encoding="utf-8")

    output = _command("--add-context", str(path))

    assert "Contexto acrescentado a 2 linhas (1 não encontradas" in output
    assert "review.csv.bak" in output


def test_the_command_needs_the_results_next_to_the_file(tmp_path):
    path = _filled_file(tmp_path)

    with pytest.raises(CommandError, match="results.json"):
        _command("--add-context", str(path))
