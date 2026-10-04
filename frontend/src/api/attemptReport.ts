import { get } from "./client";

export interface ScoreBreakdown {
  dimension: string;
  value: number;
  weight: number;
}

export interface AttemptCriterion {
  code: string;
  text: string;
  met: boolean;
}

export interface AttemptReport {
  id: number;
  scenario: string;
  level: number;
  final_score: number;
  passed: boolean;
  feedback: string;
  completed_at: string;
  hints_enabled: boolean;
  hints_used: number;
  score_breakdowns: ScoreBreakdown[];
  criteria: AttemptCriterion[];
}

/** Chamada e tipos de `GET /attempts/<id>/`: o relatório de uma tentativa concluída. */
export function fetchAttemptReport(attemptId: number, signal?: AbortSignal): Promise<AttemptReport> {
  return get<AttemptReport>(`/attempts/${attemptId}/`, { signal });
}
