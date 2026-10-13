import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from apps.agents.services.scenario_content import ScenarioContent, load_scenario_content
from apps.catalog.models import Level, Scenario

CASES_DIR = Path(__file__).parent / "cases"

NO_ADDRESSEE = "none"

STRUCTURAL_CHECKS = {
    "passes_to": "persona",
    "no_handoff": "flag",
    "single_question": "flag",
    "last_line_to_student": "flag",
    "introduces": "persona",
    "scene_resolved": "flag",
    "next_speaker": "persona",
}

_PERSONA_LINE = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)
_STUDENT_LINE = re.compile(r"^Student:\s*(.*)$", re.DOTALL)


class CaseError(ValueError):
    """Um caso de avaliação inválido: a mensagem diz qual caso e o que está errado."""


@dataclass(frozen=True)
class RouterCase:
    """Uma fala do aluno rotulada, para medir o acerto do roteador."""

    id: str
    scenario: str
    level: int
    history: list[BaseMessage]
    current: str
    line: str
    accepted: frozenset[str] | None

    @property
    def kind(self) -> str:
        """`ambiguous` sem rótulo, `answer` se o aluno só responde, `named` se chama alguém."""
        if self.accepted is None:
            return "ambiguous"
        return "answer" if NO_ADDRESSEE in self.accepted else "named"


@dataclass(frozen=True)
class Expectation:
    """O que se espera de uma rodada: uma verificação estrutural ou uma pergunta para o juiz."""

    check: str
    value: Any = None
    judge: str = ""


@dataclass(frozen=True)
class Situation:
    """Um ponto fixo da conversa, para gerar a rodada da persona várias vezes."""

    id: str
    goal: str
    scenario: str
    level: int
    samples: int
    current: str
    taking_over: bool
    addressed: bool
    turn_count: int
    history: list[BaseMessage]
    expectations: list[Expectation]


@dataclass(frozen=True)
class StudentProfile:
    """O perfil do aluno simulado de uma sessão completa."""

    id: str
    scenario: str
    level: int
    english: str
    length: str
    profile: str
    beats: dict[int, str]


@dataclass(frozen=True)
class Target:
    """A meta de uma métrica: o valor e se ele é o mínimo ou o máximo aceitável."""

    metric: str
    goal: float
    direction: str
    label: str


@dataclass
class LoadedCases:
    """Todos os casos já validados, e o conteúdo de execução de cada cenário e nível usado."""

    router: list[RouterCase] = field(default_factory=list)
    situations: list[Situation] = field(default_factory=list)
    students: list[StudentProfile] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    contents: dict[tuple[str, int], ScenarioContent] = field(default_factory=dict)


def _read(directory: Path, name: str) -> dict:
    path = directory / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CaseError(f"Arquivo de casos não encontrado: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise CaseError(f"{name} não é um JSON válido: {exc}.") from exc


class _Resolver:
    """Resolve cenário, nível e personas de cada caso, guardando o conteúdo carregado."""

    def __init__(self, contents: dict[tuple[str, int], ScenarioContent]):
        self.contents = contents

    def content(self, case_id: str, scenario: str, level: int) -> ScenarioContent:
        key = (scenario, level)
        if key not in self.contents:
            scenario_row = Scenario.objects.filter(slug=scenario).first()
            if scenario_row is None:
                raise CaseError(f"Caso '{case_id}': o cenário '{scenario}' não existe.")
            level_row = Level.objects.filter(order=level).first()
            if level_row is None:
                raise CaseError(f"Caso '{case_id}': o nível {level} não existe.")
            self.contents[key] = load_scenario_content(scenario_row, level_row)
        return self.contents[key]

    def persona(self, case_id: str, content: ScenarioContent, key: str) -> str:
        if key not in content.role_keys():
            raise CaseError(
                f"Caso '{case_id}': '{key}' não é uma persona do cenário '{content.slug}' "
                f"(personas: {', '.join(content.role_keys())})."
            )
        return key


def _history(
    case_id: str, lines: list[str], named: dict[str, list[str]], content: ScenarioContent
) -> list[BaseMessage]:
    expanded: list[str] = []
    for line in lines:
        if line.startswith("@"):
            if line[1:] not in named:
                raise CaseError(f"Caso '{case_id}': a conversa '{line[1:]}' não está definida.")
            expanded.extend(named[line[1:]])
        else:
            expanded.append(line)
    names = {role.name for role in content.roles}
    messages: list[BaseMessage] = []
    for line in expanded:
        student = _STUDENT_LINE.match(line)
        persona = _PERSONA_LINE.match(line)
        if student:
            messages.append(HumanMessage(content=student.group(1).strip()))
        elif persona and persona.group(1) in names:
            messages.append(AIMessage(content=f"[{persona.group(1)}] {persona.group(2).strip()}"))
        elif persona:
            raise CaseError(
                f"Caso '{case_id}': '{persona.group(1)}' não é uma persona do cenário "
                f"'{content.slug}' ({', '.join(sorted(names))})."
            )
        else:
            raise CaseError(
                f"Caso '{case_id}': a fala '{line[:40]}' precisa começar com 'Student:' "
                "ou com '[Nome da persona]'."
            )
    return messages


def _router_cases(directory: Path, resolver: _Resolver) -> list[RouterCase]:
    data = _read(directory, "router.json")
    named = data.get("histories", {})
    cases = []
    for raw in data.get("cases", []):
        case_id = raw.get("id", "?")
        for required in ("scenario", "history", "current", "line"):
            if required not in raw:
                raise CaseError(f"Caso '{case_id}': falta o campo '{required}'.")
        level = raw.get("level", 3)
        content = resolver.content(case_id, raw["scenario"], level)
        if raw["history"] not in named:
            raise CaseError(f"Caso '{case_id}': a conversa '{raw['history']}' não está definida.")
        history = _history(case_id, list(named[raw["history"]]), named, content)
        current = resolver.persona(case_id, content, raw["current"])
        accepted = raw.get("accepted")
        if accepted is not None:
            for key in accepted:
                if key != NO_ADDRESSEE:
                    resolver.persona(case_id, content, key)
            accepted = frozenset(accepted)
        cases.append(
            RouterCase(case_id, raw["scenario"], level, history, current, raw["line"], accepted)
        )
    return cases


def _expectation(case_id: str, raw: dict, content: ScenarioContent, resolver: _Resolver):
    if "judge" in raw:
        if not str(raw["judge"]).strip():
            raise CaseError(f"Caso '{case_id}': a pergunta para o juiz está vazia.")
        return Expectation(check="judge", judge=str(raw["judge"]).strip())
    check = raw.get("check")
    if check not in STRUCTURAL_CHECKS:
        raise CaseError(
            f"Caso '{case_id}': verificação '{check}' desconhecida "
            f"(use: {', '.join(STRUCTURAL_CHECKS)} ou 'judge')."
        )
    value = raw.get("value")
    if STRUCTURAL_CHECKS[check] == "persona":
        resolver.persona(case_id, content, str(value))
    elif not isinstance(value, bool):
        raise CaseError(f"Caso '{case_id}': a verificação '{check}' espera true ou false.")
    return Expectation(check=check, value=value)


def _situations(directory: Path, resolver: _Resolver) -> list[Situation]:
    data = _read(directory, "situations.json")
    named = data.get("histories", {})
    situations = []
    for raw in data.get("situations", []):
        case_id = raw.get("id", "?")
        for required in ("scenario", "level", "samples", "current", "history", "expect"):
            if required not in raw:
                raise CaseError(f"Caso '{case_id}': falta o campo '{required}'.")
        if int(raw["samples"]) < 1:
            raise CaseError(f"Caso '{case_id}': 'samples' precisa ser pelo menos 1.")
        content = resolver.content(case_id, raw["scenario"], raw["level"])
        situations.append(
            Situation(
                id=case_id,
                goal=raw.get("goal", ""),
                scenario=raw["scenario"],
                level=raw["level"],
                samples=int(raw["samples"]),
                current=resolver.persona(case_id, content, raw["current"]),
                taking_over=bool(raw.get("taking_over", False)),
                addressed=bool(raw.get("addressed", False)),
                turn_count=int(raw.get("turn_count", 1)),
                history=_history(case_id, list(raw["history"]), named, content),
                expectations=[
                    _expectation(case_id, item, content, resolver) for item in raw["expect"]
                ],
            )
        )
    return situations


def _students(directory: Path, resolver: _Resolver) -> list[StudentProfile]:
    data = _read(directory, "students.json")
    profiles = []
    for raw in data.get("sessions", []):
        case_id = raw.get("id", "?")
        for required in ("scenario", "level", "english", "length", "profile"):
            if required not in raw:
                raise CaseError(f"Caso '{case_id}': falta o campo '{required}'.")
        resolver.content(case_id, raw["scenario"], raw["level"])
        beats = {}
        for turn, instruction in raw.get("beats", {}).items():
            if not str(turn).isdigit() or int(turn) < 1:
                raise CaseError(
                    f"Caso '{case_id}': a fala '{turn}' das instruções não é um número."
                )
            beats[int(turn)] = instruction
        profiles.append(
            StudentProfile(
                case_id, raw["scenario"], raw["level"], raw["english"], raw["length"],
                raw["profile"], beats,
            )
        )
    return profiles


def _targets(directory: Path) -> list[Target]:
    data = _read(directory, "targets.json")
    targets = []
    for raw in data.get("targets", []):
        if raw.get("direction") not in ("min", "max"):
            raise CaseError(f"Meta '{raw.get('metric', '?')}': 'direction' deve ser min ou max.")
        targets.append(Target(raw["metric"], float(raw["goal"]), raw["direction"], raw["label"]))
    return targets


def load_cases(directory: Path = CASES_DIR) -> LoadedCases:
    """Carrega e valida todos os casos antes de qualquer chamada a modelo.

    Um cenário, nível ou persona que não existe, uma conversa mal escrita ou uma verificação
    desconhecida interrompe com uma mensagem que diz qual caso e o que está errado: descobrir
    isso no meio da execução custaria chamadas pagas e deixaria a medição pela metade.
    """
    contents: dict[tuple[str, int], ScenarioContent] = {}
    resolver = _Resolver(contents)
    return LoadedCases(
        router=_router_cases(directory, resolver),
        situations=_situations(directory, resolver),
        students=_students(directory, resolver),
        targets=_targets(directory),
        contents=contents,
    )
