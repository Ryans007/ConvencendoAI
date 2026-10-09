import type { RoundItem } from "../../api/reviewRound";

const MS_PER_DAY = 24 * 60 * 60 * 1000;
const BOX_INTERVALS = [1, 3, 7, 14, 30];

/** Quanto tempo faz que o aluno cometeu o erro, em dias de calendário do próprio aluno. */
export function ageLabel(occurredAt: string, now: Date): string {
  const occurred = new Date(occurredAt);
  const day = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.round((day(now).getTime() - day(occurred).getTime()) / MS_PER_DAY);
  if (days <= 0) {
    return "hoje";
  }
  return days === 1 ? "ontem" : `há ${days} dias`;
}

/** A cena onde o aluno errou e há quanto tempo, como o cartão mostra no alto. */
export function originLabel(item: RoundItem, now: Date): string {
  return `${item.scenario_title} · ${ageLabel(item.occurred_at, now)}`;
}

/** O intervalo atual do item, ou "Dominado" quando ele já passou da caixa de 30 dias. */
export function intervalLabel(item: RoundItem): string {
  if (item.mastered) {
    return "Dominado";
  }
  return `Intervalo de ${item.interval_days} ${item.interval_days === 1 ? "dia" : "dias"}`;
}

/** Quantos dos 5 tracinhos da caixa ficam preenchidos: todos quando o item está dominado. */
export function filledBoxes(item: RoundItem): number {
  if (item.mastered) {
    return BOX_INTERVALS.length;
  }
  const index = BOX_INTERVALS.indexOf(item.interval_days);
  return index === -1 ? 1 : index + 1;
}
