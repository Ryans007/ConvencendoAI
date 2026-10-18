import json
from dataclasses import replace
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.agents.evaluation.runner import (
    BudgetExceeded,
    EvaluationOptions,
    estimate_calls,
    load_cases,
    run_evaluation,
    select_cases,
)
from apps.agents.evaluation.schemas import SemanticVerdict, StudentReply
from apps.agents.services.schemas import ClosingLine, PersonaTurn, RoutingDecision
from apps.agents.tests.evaluation.fakes import JUDGE, PERSONA, ROUTER, FakeModels, role_verdict
from apps.llm.models import AgentModelConfig, LLMModel, LLMProvider
from apps.usage.services.owner import current_owner

pytestmark = pytest.mark.django_db


def _fakes(monkeypatch, *, persona=None) -> FakeModels:
    models = FakeModels().install(monkeypatch)
    models.set(
        PERSONA,
        "PersonaTurn",
        persona
        or [
            PersonaTurn(line="Hello, I'm Rachel. What is going on?", pass_to="student"),
            PersonaTurn(
                line="Understood. The new deadline is next Friday.",
                pass_to="student",
                scene_resolved=True,
            ),
        ],
    )
    models.set(PERSONA, "ClosingLine", ClosingLine(line="Thank you, bye."))
    models.set(ROUTER, "RoutingDecision", RoutingDecision(speaker="none"))
    models.set(JUDGE, "StudentReply", StudentReply(line="I need one more week."))
    models.set(JUDGE, "RoleVerdict", role_verdict())
    models.set(JUDGE, "SemanticVerdict", SemanticVerdict(answer="yes", reason="sim"))
    return models


def _options(tmp_path, **changes) -> EvaluationOptions:
    values = dict(
        scenario="negociar-prazo",
        level=3,
        samples=1,
        repetitions=1,
        output_dir=tmp_path,
        label="teste",
        seed=1,
    )
    values.update(changes)
    return EvaluationOptions(**values)


def test_the_estimate_counts_the_calls_of_each_layer_and_the_filter(tmp_path):
    cases = select_cases(load_cases(), _options(tmp_path))

    estimate = estimate_calls(cases, _options(tmp_path))

    assert estimate["router"] == len(cases.router)
    assert estimate["situations"] > 0 and estimate["sessions"] > 0
    assert all(case.scenario == "negociar-prazo" for case in cases.router)


def test_turning_the_judge_off_lowers_the_estimate(tmp_path):
    cases = select_cases(load_cases(), _options(tmp_path))

    with_judge = sum(estimate_calls(cases, _options(tmp_path)).values())
    without = sum(estimate_calls(cases, _options(tmp_path, use_judge=False)).values())

    assert without < with_judge


def test_a_layer_that_was_not_asked_costs_nothing(tmp_path):
    options = _options(tmp_path, layers=("router",))
    cases = select_cases(load_cases(), options)

    estimate = estimate_calls(cases, options)

    assert estimate["situations"] == 0 and estimate["sessions"] == 0


def test_above_the_ceiling_the_run_refuses_before_any_call(tmp_path, monkeypatch):
    models = _fakes(monkeypatch)

    with pytest.raises(BudgetExceeded, match="teto é 10"):
        run_evaluation(_options(tmp_path, max_calls=10))

    assert models.calls == []
    assert list(tmp_path.iterdir()) == []


def test_a_full_run_writes_the_report_and_the_raw_data(tmp_path, monkeypatch):
    _fakes(monkeypatch)

    folder, estimate = run_evaluation(_options(tmp_path))

    report = (folder / "report.md").read_text(encoding="utf-8")
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    assert folder.parent == tmp_path and folder.name.endswith("-teste")
    assert "# Avaliação da conversa — teste" in report
    assert "## Placar" in report and "## Roteador" in report
    assert "## Situações fixas" in report and "## Sessões completas" in report
    assert "## Papel das personas (juiz)" in report and "## Consumo" in report
    assert "S2-deadline-negotiation" in report
    assert data["layers"] == ["router", "situations", "sessions"]
    assert data["sessions"][0]["scene_resolved"] is True
    assert sum(estimate.values()) == data["calls_estimated"]


def test_the_scorecard_in_the_report_marks_each_target(tmp_path, monkeypatch):
    _fakes(monkeypatch)

    folder, _ = run_evaluation(_options(tmp_path))

    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    statuses = {row["metric"]: row["status"] for row in data["scorecard"]}
    assert statuses["router_named_accuracy"] == "falhou"
    assert statuses["session_dangling_rounds"] == "ok"
    assert statuses["role_pass_rate"] == "ok"
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert "| ✘ | Roteador: acerta a persona que o aluno chamou pelo nome |" in report


def test_the_run_is_marked_as_evaluation_usage(tmp_path, monkeypatch):
    owners = []

    def persona(messages):
        owner = current_owner()
        owners.append(owner.username if owner else None)
        return PersonaTurn(line="What happened?", pass_to="student", scene_resolved=False)

    _fakes(monkeypatch, persona=persona)

    run_evaluation(_options(tmp_path, layers=("situations",), use_judge=False))

    assert owners and set(owners) == {"avaliação"}
    assert current_owner() is None


def test_the_chosen_model_is_used_only_during_the_run(tmp_path, monkeypatch):
    provider = LLMProvider.objects.create(
        code="groq", name="Groq", base_url="https://x/v1", api_key_env="LLM_TEST_API_KEY"
    )
    small = LLMModel.objects.create(provider=provider, model_id="small", display_name="s")
    large = LLMModel.objects.create(provider=provider, model_id="large", display_name="l")
    config = AgentModelConfig.get_solo()
    config.persona_model = small
    config.save()
    _fakes(monkeypatch)

    folder, _ = run_evaluation(_options(tmp_path, models={"persona": large}, layers=("router",)))

    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    assert data["models"]["persona"] == "groq/large"
    assert data["overridden"] == ["persona"]
    assert AgentModelConfig.get_solo().persona_model_id == small.pk


def test_without_the_judge_no_verdict_is_requested(tmp_path, monkeypatch):
    models = _fakes(monkeypatch)

    folder, _ = run_evaluation(_options(tmp_path, use_judge=False))

    assert (JUDGE, "RoleVerdict") not in models.calls
    assert (JUDGE, "SemanticVerdict") not in models.calls
    assert "## Papel das personas" not in (folder / "report.md").read_text(encoding="utf-8")


def test_a_calibration_sample_is_exported_next_to_the_report(tmp_path, monkeypatch):
    _fakes(monkeypatch)

    folder, _ = run_evaluation(_options(tmp_path, calibration_sample=5))

    assert (folder / "review.csv").exists()


def test_no_review_file_without_the_request(tmp_path, monkeypatch):
    _fakes(monkeypatch)

    folder, _ = run_evaluation(_options(tmp_path))

    assert not (folder / "review.csv").exists()


def _command(*args):
    out = StringIO()
    call_command("evaluate_conversation", *args, stdout=out)
    return out.getvalue()


def test_the_dry_run_shows_the_estimate_and_calls_nothing(monkeypatch):
    models = _fakes(monkeypatch)

    output = _command("--dry-run", "--scenario", "negociar-prazo")

    assert "Estimativa de chamadas" in output and "Nenhuma chamada foi feita" in output
    assert models.calls == []


def test_the_command_runs_and_points_to_the_report(tmp_path, monkeypatch):
    _fakes(monkeypatch)

    output = _command(
        "--scenario", "negociar-prazo", "--level", "3", "--samples", "1", "--repetitions", "1",
        "--output-dir", str(tmp_path), "--label", "cli",
    )

    assert "Relatório em" in output and "report.md" in output
    assert len(list(tmp_path.glob("*-cli/report.md"))) == 1


def test_an_unknown_layer_is_refused():
    with pytest.raises(CommandError, match="Camada desconhecida: voz"):
        _command("--layers", "router,voz")


def test_a_model_that_does_not_exist_is_refused():
    with pytest.raises(CommandError, match="Nenhum modelo de chat cadastrado"):
        _command("--persona-model", "modelo-fantasma", "--dry-run")


def test_a_model_id_shared_by_two_providers_asks_for_the_number():
    for code in ("a", "b"):
        provider = LLMProvider.objects.create(
            code=code, name=code, base_url="https://x/v1", api_key_env="LLM_TEST_API_KEY"
        )
        LLMModel.objects.create(provider=provider, model_id="twin", display_name="twin")

    with pytest.raises(CommandError, match="use o número"):
        _command("--persona-model", "twin", "--dry-run")


def test_a_model_is_found_by_its_number(monkeypatch):
    provider = LLMProvider.objects.create(
        code="a", name="a", base_url="https://x/v1", api_key_env="LLM_TEST_API_KEY"
    )
    model = LLMModel.objects.create(provider=provider, model_id="solo", display_name="solo")
    _fakes(monkeypatch)

    output = _command("--persona-model", str(model.pk), "--dry-run")

    assert "Nenhuma chamada foi feita" in output


def test_the_ceiling_stops_the_command_with_a_clear_message():
    with pytest.raises(CommandError, match="o teto é 5"):
        _command("--max-calls", "5")


def test_the_command_reports_a_case_error_before_any_call(monkeypatch):
    models = _fakes(monkeypatch)

    def broken(*args, **kwargs):
        from apps.agents.evaluation.case_loader import CaseError

        raise CaseError("Caso 'X': quebrado.")

    monkeypatch.setattr("apps.agents.evaluation.runner.load_cases", broken)
    monkeypatch.setattr("apps.agents.management.commands.evaluate_conversation.load_cases", broken)

    with pytest.raises(CommandError, match="Caso 'X'"):
        _command("--dry-run")

    assert models.calls == []


def test_the_calibration_mode_prints_the_agreement(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(
        "id,source,line,item,item_label,judge,reason,human\n"
        "1,P1,[Tom] a,english_only,Só inglês,yes,ok,yes\n"
        "2,P1,[Tom] b,no_task_reveal,Não entrega a tarefa,no,x,yes\n",
        encoding="utf-8-sig",
    )

    output = _command("--calibrate", str(path))

    assert "Concordância: 50% em 2 itens revisados" in output
    assert "discordou em no_task_reveal" in output


def test_the_calibration_mode_needs_an_existing_file(tmp_path):
    with pytest.raises(CommandError, match="não encontrado"):
        _command("--calibrate", str(tmp_path / "nada.csv"))


def test_the_calibration_mode_needs_a_reviewed_file(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(
        "id,source,line,item,item_label,judge,reason,human\n1,P1,[Tom] a,english_only,x,yes,ok,\n",
        encoding="utf-8-sig",
    )

    with pytest.raises(CommandError, match="Nenhuma linha"):
        _command("--calibrate", str(path))


def test_a_situation_through_the_director_costs_one_more_call_per_sample(tmp_path):
    cases = select_cases(load_cases(), _options(tmp_path, scenario="entrevista-de-emprego"))
    options = _options(tmp_path, scenario="entrevista-de-emprego", layers=("situations",))
    direct = [s for s in cases.situations if s.direct]
    plain = replace(cases, situations=[replace(s, direct=False) for s in direct])
    only_direct = replace(cases, situations=direct)

    with_director = estimate_calls(only_direct, options)["situations"]
    without_director = estimate_calls(plain, options)["situations"]

    assert with_director - without_director == len(direct)


def test_the_report_shows_the_topic_accuracy_and_the_router_time(tmp_path, monkeypatch):
    _fakes(monkeypatch)

    folder, _ = run_evaluation(_options(tmp_path, layers=("router",), use_judge=False))

    report = (folder / "report.md").read_text(encoding="utf-8")
    assert "Dono do assunto:" in report
    assert "Erros de assunto:" in report
