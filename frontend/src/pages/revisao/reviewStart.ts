import type { ReviewSummary } from "../../api/reviewSummary";

/** Intervalos que o item percorre até ser dado como dominado, na ordem em que o aluno os vê. */
export const REVIEW_INTERVAL_LABELS = ["1 dia", "3 dias", "7 dias", "14 dias", "30 dias"] as const;

const MS_PER_DAY = 24 * 60 * 60 * 1000;

export type ReviewStart =
  | { kind: "due"; title: string }
  | { kind: "none"; nextReview: string }
  | { kind: "empty" };

/** Lê "AAAA-MM-DD" como a data de calendário local, sem hora, para o fuso não mudar o dia. */
function parseLocalDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Descreve o vencimento em relação ao dia de hoje do aluno: "amanhã" ou "em N dias". */
export function nextReviewText(nextDueOn: string, today: Date): string {
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const days = Math.round((parseLocalDate(nextDueOn).getTime() - todayStart.getTime()) / MS_PER_DAY);
  return days <= 1 ? "A próxima revisão é amanhã." : `A próxima revisão é em ${days} dias.`;
}

/**
 * Estado da tela inicial da Revisão: com itens vencidos, sem vencidos mas com um próximo
 * vencimento, ou sem nenhum item. O dia de hoje entra como argumento para o teste fixá-lo.
 */
export function reviewStart(summary: ReviewSummary, today: Date): ReviewStart {
  if (summary.due > 0) {
    const noun = summary.due === 1 ? "item" : "itens";
    return { kind: "due", title: `Você tem ${summary.due} ${noun} para revisar` };
  }
  if (summary.next_due_on !== null) {
    return { kind: "none", nextReview: nextReviewText(summary.next_due_on, today) };
  }
  return { kind: "empty" };
}
