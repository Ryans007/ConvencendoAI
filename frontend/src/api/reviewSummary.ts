import { get } from "./client";

/** Quantos itens de revisão do aluno estão vencidos e quando vence o próximo. */
export interface ReviewSummary {
  due: number;
  next_due_on: string | null;
}

/** Chamada e tipos de `GET /review/summary/`: o resumo da revisão do aluno autenticado. */
export function fetchReviewSummary(signal?: AbortSignal): Promise<ReviewSummary> {
  return get<ReviewSummary>("/review/summary/", { signal });
}
