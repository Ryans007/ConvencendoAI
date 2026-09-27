import { get } from "./client";

export interface BriefingRole {
  name: string;
  scene_function: string;
  archetype: string;
}

export interface ScenarioBriefing {
  title: string;
  objective: string;
  context: string;
  difficulty_label: string;
  expected_cefr: string;
  max_turns: number;
  roles: BriefingRole[];
  memory_summary: string;
}

/** Chamada e tipos de `GET /scenarios/<slug>/levels/<order>/briefing/`. */
export function fetchScenarioBriefing(
  scenarioSlug: string,
  levelOrder: number,
  signal?: AbortSignal,
): Promise<ScenarioBriefing> {
  return get<ScenarioBriefing>(`/scenarios/${scenarioSlug}/levels/${levelOrder}/briefing/`, { signal });
}
