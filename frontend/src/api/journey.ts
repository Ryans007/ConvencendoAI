import { get } from "./client";

/** Resumo da última tentativa concluída de um nível, aprovada ou não. */
export interface LastAttempt {
  id: number;
  final_score: number;
  passed: boolean;
  completed_at: string;
}

export interface LevelState {
  order: number;
  name: string;
  expected_cefr: string;
  approved: boolean;
  available: boolean;
  cooldown_remaining_seconds: number | null;
  last_attempt: LastAttempt | null;
}

export interface ScenarioState {
  slug: string;
  title: string;
  order: number;
  completed: boolean;
  unlocked: boolean;
  level_states: LevelState[];
}

export interface TrackState {
  slug: string;
  title: string;
  order: number;
  student_role: string;
  unlocked: boolean;
  completed: boolean;
  approved_levels: number;
  possible_levels: number;
  performance: number | null;
  scenario_states: ScenarioState[];
}

/** Chamada e tipos de `GET /journey/`: a jornada inteira do aluno autenticado. */
export function fetchJourney(signal?: AbortSignal): Promise<TrackState[]> {
  return get<TrackState[]>("/journey/", { signal });
}
