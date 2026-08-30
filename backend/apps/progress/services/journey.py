from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.catalog.models import Level, Scenario, Track
from apps.progress.models import Attempt


@dataclass
class LevelState:
    """Estado calculado de um nível dentro de um cenário, para um aluno."""

    level: Level
    approved: bool
    cooldown_remaining: timedelta | None

    @property
    def available(self) -> bool:
        return self.cooldown_remaining is None


@dataclass
class ScenarioState:
    """Estado calculado de um cenário, para um aluno."""

    scenario: Scenario
    completed: bool
    unlocked: bool
    level_states: list[LevelState]


@dataclass
class TrackState:
    """Estado calculado de uma trilha, para um aluno."""

    track: Track
    unlocked: bool
    completed: bool
    approved_levels: int
    possible_levels: int
    performance: float | None
    scenario_states: list[ScenarioState]


def build_journey(user) -> list[TrackState]:
    """Monta o estado completo da jornada de um aluno numa quantidade constante de
    consultas ao banco, independente do número de cenários existentes: todas as
    tentativas do aluno são carregadas de uma vez, e o estado de cada nível, cenário
    e trilha é calculado em memória a partir delas.
    """
    tracks = list(Track.objects.order_by("order").prefetch_related("scenarios"))
    levels = list(Level.objects.order_by("order"))
    attempts = list(Attempt.objects.filter(user=user).select_related("level"))
    now = timezone.now()

    attempts_by_scenario_level: dict[tuple[int, int], list[Attempt]] = defaultdict(list)
    scenario_completed: dict[int, bool] = defaultdict(bool)
    scenario_best: dict[int, tuple[int, int]] = {}

    for attempt in attempts:
        attempts_by_scenario_level[(attempt.scenario_id, attempt.level_id)].append(attempt)
        if not attempt.passed:
            continue
        scenario_completed[attempt.scenario_id] = True
        candidate = (attempt.level.order, attempt.final_score)
        current = scenario_best.get(attempt.scenario_id)
        if current is None or candidate[0] > current[0]:
            scenario_best[attempt.scenario_id] = candidate

    track_states: list[TrackState] = []
    for track in tracks:
        track_unlocked = track_states[-1].completed if track_states else True
        scenarios = sorted(track.scenarios.all(), key=lambda scenario: scenario.order)

        scenario_states: list[ScenarioState] = []
        previous_completed = True
        for scenario in scenarios:
            completed = scenario_completed.get(scenario.id, False)
            unlocked = track_unlocked and previous_completed

            level_states = []
            for level in levels:
                scenario_level_attempts = attempts_by_scenario_level.get(
                    (scenario.id, level.id), []
                )
                approved = any(attempt.passed for attempt in scenario_level_attempts)
                last_completed = max(
                    (
                        attempt.completed_at
                        for attempt in scenario_level_attempts
                        if attempt.completed_at is not None
                    ),
                    default=None,
                )
                remaining = None
                if last_completed is not None:
                    release_at = last_completed + timedelta(hours=scenario.cooldown_hours)
                    delta = release_at - now
                    if delta > timedelta(0):
                        remaining = delta
                level_states.append(
                    LevelState(level=level, approved=approved, cooldown_remaining=remaining)
                )

            scenario_states.append(
                ScenarioState(
                    scenario=scenario,
                    completed=completed,
                    unlocked=unlocked,
                    level_states=level_states,
                )
            )
            previous_completed = completed

        possible_levels = len(scenarios) * len(levels)
        approved_levels = sum(
            1
            for scenario_state in scenario_states
            for level_state in scenario_state.level_states
            if level_state.approved
        )
        scores = [
            scenario_best[scenario.id][1] for scenario in scenarios if scenario.id in scenario_best
        ]
        performance = sum(scores) / len(scores) if scores else None
        track_completed = bool(scenario_states) and all(
            scenario_state.completed for scenario_state in scenario_states
        )

        track_states.append(
            TrackState(
                track=track,
                unlocked=track_unlocked,
                completed=track_completed,
                approved_levels=approved_levels,
                possible_levels=possible_levels,
                performance=performance,
                scenario_states=scenario_states,
            )
        )

    return track_states
