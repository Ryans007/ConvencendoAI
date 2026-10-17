from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.agents.evaluation import calibration
from apps.agents.evaluation.case_loader import CaseError
from apps.agents.evaluation.runner import (
    ALL_LAYERS,
    DEFAULT_MAX_CALLS,
    DEFAULT_OUTPUT_DIR,
    BudgetExceeded,
    EvaluationOptions,
    estimate_calls,
    load_cases,
    run_evaluation,
    select_cases,
)
from apps.llm.constants import ModelCategory
from apps.llm.models import LLMModel

_ROLE_OPTIONS = {"persona": "persona_model", "router": "router_model", "judge": "judge_model"}


def resolve_model(value: str) -> LLMModel:
    """Acha um modelo de chat cadastrado pelo id numérico ou pelo `model_id`, sem ambiguidade."""
    candidates = LLMModel.objects.filter(category=ModelCategory.CHAT).select_related("provider")
    matches = (
        candidates.filter(pk=int(value)) if value.isdigit() else candidates.filter(model_id=value)
    )
    found = list(matches)
    if not found:
        raise CommandError(f"Nenhum modelo de chat cadastrado combina com '{value}'.")
    if len(found) > 1:
        options = ", ".join(f"{m.pk} ({m.provider.code}/{m.model_id})" for m in found)
        raise CommandError(f"'{value}' combina com mais de um modelo; use o número: {options}.")
    return found[0]


class Command(BaseCommand):
    """Mede a troca entre as personas e o respeito ao papel, com os modelos reais."""

    help = (
        "Avalia a sessão de conversa em três camadas (roteador, situações fixas e sessões "
        "completas com um aluno simulado) e grava um relatório em português."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--layers", default=",".join(ALL_LAYERS), help="camadas a rodar, separadas por vírgula"
        )
        parser.add_argument("--scenario", default="", help="só este cenário (slug)")
        parser.add_argument("--level", type=int, default=None, help="só este nível (1, 2 ou 3)")
        parser.add_argument("--samples", type=int, default=None, help="amostras por situação")
        parser.add_argument("--repetitions", type=int, default=2, help="repetições do roteador")
        parser.add_argument(
            "--no-judge", action="store_true", help="não chama o juiz (mais barato)"
        )
        for role in _ROLE_OPTIONS:
            parser.add_argument(
                f"--{role}-model",
                default="",
                help=f"modelo do papel '{role}' só nesta execução (id numérico ou model_id)",
            )
        parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
        parser.add_argument(
            "--label", default="run", help="nome da execução, na pasta e no relatório"
        )
        parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
        parser.add_argument("--dry-run", action="store_true", help="só mostra a estimativa")
        parser.add_argument(
            "--calibration-sample",
            type=int,
            default=0,
            help="exporta N itens julgados para revisão humana (review.csv)",
        )
        parser.add_argument(
            "--seed", type=int, default=None, help="semente da amostra de calibração"
        )
        parser.add_argument(
            "--calibrate",
            default="",
            help="calcula a concordância do juiz com o review.csv revisado e sai",
        )
        parser.add_argument(
            "--add-context",
            default="",
            help="acrescenta a coluna de contexto a um review.csv já preenchido e sai",
        )

    def handle(self, *args, **options) -> None:
        if options["calibrate"]:
            self._calibrate(Path(options["calibrate"]))
            return
        if options["add_context"]:
            self._add_context(Path(options["add_context"]))
            return
        layers = tuple(part.strip() for part in options["layers"].split(",") if part.strip())
        unknown = [layer for layer in layers if layer not in ALL_LAYERS]
        if unknown:
            raise CommandError(
                f"Camada desconhecida: {', '.join(unknown)}. Use {', '.join(ALL_LAYERS)}."
            )
        models = {
            role: resolve_model(options[f"{role}_model"])
            for role in _ROLE_OPTIONS
            if options[f"{role}_model"]
        }
        evaluation = EvaluationOptions(
            layers=layers,
            scenario=options["scenario"],
            level=options["level"],
            samples=options["samples"],
            repetitions=options["repetitions"],
            use_judge=not options["no_judge"],
            models=models,
            max_calls=options["max_calls"],
            label=options["label"],
            calibration_sample=options["calibration_sample"],
            output_dir=Path(options["output_dir"]),
            seed=options["seed"],
        )
        try:
            if options["dry_run"]:
                self._dry_run(evaluation)
                return
            folder, estimate = run_evaluation(evaluation, progress=self._progress)
        except (CaseError, BudgetExceeded) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Chamadas no máximo previstas: {sum(estimate.values())} {estimate}")
        self.stdout.write(self.style.SUCCESS(f"Relatório em {folder / 'report.md'}"))

    def _progress(self, message: str) -> None:
        self.stdout.write(f"  {message}")

    def _dry_run(self, evaluation: EvaluationOptions) -> None:
        cases = select_cases(load_cases(), evaluation)
        estimate = estimate_calls(cases, evaluation)
        self.stdout.write(f"Estimativa de chamadas, no máximo: {sum(estimate.values())} {estimate}")
        self.stdout.write(f"Teto: {evaluation.max_calls}. Nenhuma chamada foi feita.")

    def _add_context(self, path: Path) -> None:
        results = path.parent / "results.json"
        if not path.exists() or not results.exists():
            raise CommandError(
                f"Preciso do arquivo {path} e do results.json da mesma pasta ({results})."
            )
        done = calibration.add_context(path, results, load_cases())
        self.stdout.write(
            f"Contexto acrescentado a {done['found']} linhas "
            f"({done['missing']} não encontradas nos resultados). "
            f"A cópia do arquivo original ficou em {path.name}.bak."
        )

    def _calibrate(self, path: Path) -> None:
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}.")
        result = calibration.read_agreement(path)
        if result["agreement"] is None:
            raise CommandError("Nenhuma linha do arquivo foi revisada (coluna 'human' vazia).")
        self.stdout.write(
            f"Concordância: {result['agreement']:.0%} em {result['reviewed']} itens revisados "
            f"({result['skipped']} sem resposta)."
        )
        for item, (agreed, total) in sorted(result["by_item"].items()):
            self.stdout.write(f"  {item}: {agreed} de {total}")
        for row in result["disagreements"]:
            self.stdout.write(
                f"  discordou em {row['item']}: {row['line']} "
                f"(juiz: {row['judge']}; você: {row['human']})"
            )
