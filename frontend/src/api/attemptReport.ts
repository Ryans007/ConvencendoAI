import { get, getBlob } from "./client";

export interface ScoreBreakdown {
  dimension: string;
  value: number;
  weight: number;
  comment: string;
}

export interface AttemptCriterion {
  code: string;
  text: string;
  met: boolean;
}

export interface AttemptMistake {
  id: number;
  produced: string;
  correct: string;
  explanation: string;
  examples: string[];
}

export interface SpeechMetrics {
  reaction_seconds: number | null;
  words_per_minute: number | null;
  long_pauses_per_100_words: number | null;
  lexical_diversity: number | null;
  lexical_range: number | null;
}

export interface FluencyShares {
  measured_share: number;
  reaction_share: number;
  speed_share: number;
  pauses_share: number;
}

export interface VocabularyShares {
  judged_share: number;
  diversity_share: number;
  range_share: number;
}

export interface ReportScoring {
  passing_score: number;
  fluency: FluencyShares | null;
  vocabulary: VocabularyShares | null;
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
  mistakes: AttemptMistake[];
  speech_metrics: SpeechMetrics | null;
  scoring: ReportScoring;
}

/** Chamada e tipos de `GET /attempts/<id>/`: o relatório de uma tentativa concluída. */
export function fetchAttemptReport(attemptId: number, signal?: AbortSignal): Promise<AttemptReport> {
  return get<AttemptReport>(`/attempts/${attemptId}/`, { signal });
}

/** Chamada de `GET /attempts/<id>/mistakes/<id>/audio/`: o áudio da forma correta de um erro. */
export function fetchMistakeAudio(attemptId: number, mistakeId: number): Promise<Blob> {
  return getBlob(`/attempts/${attemptId}/mistakes/${mistakeId}/audio/`);
}
