import type { AnswerResponse, Attempt, RoundItem, Step } from "../api/reviewRound";

export type RoundPhase =
  | "loading"
  | "empty"
  | "idle"
  | "recording"
  | "analyzing"
  | "result"
  | "not_heard"
  | "too_many"
  | "unavailable"
  | "mic_denied"
  | "confirm_discard"
  | "summary";

export type FinishedKind = "advanced" | "repeat" | "back" | "mastered" | "discarded";

/** Um item da rodada que já terminou, com o que aconteceu com ele no calendário. */
export interface FinishedItem {
  item: RoundItem;
  kind: FinishedKind;
  intervalDays: number | null;
}

export interface RoundState {
  phase: RoundPhase;
  items: RoundItem[];
  index: number;
  step: Step;
  attempt: Attempt;
  reference: string;
  last: AnswerResponse | null;
  phaseBeforeDiscard: RoundPhase;
  finished: FinishedItem[];
}

export type RoundEvent =
  | { type: "loaded"; items: RoundItem[] }
  | { type: "recordingStarted" }
  | { type: "micDenied" }
  | { type: "tooShort" }
  | { type: "submitted" }
  | { type: "answered"; response: AnswerResponse }
  | { type: "failed" }
  | { type: "tooMany" }
  | { type: "retry" }
  | { type: "continue" }
  | { type: "askDiscard" }
  | { type: "cancelDiscard" }
  | { type: "discarded" };

export const INITIAL_ROUND_STATE: RoundState = {
  phase: "loading",
  items: [],
  index: 0,
  step: 1,
  attempt: 1,
  reference: "",
  last: null,
  phaseBeforeDiscard: "idle",
  finished: [],
};

const CAN_RECORD: RoundPhase[] = ["idle", "not_heard", "too_many", "mic_denied"];
const CAN_DISCARD: RoundPhase[] = [
  "idle",
  "not_heard",
  "too_many",
  "mic_denied",
  "unavailable",
  "result",
];

function startItem(state: RoundState, index: number): RoundState {
  const item = state.items[index];
  return {
    ...state,
    phase: "idle",
    index,
    step: item.step,
    attempt: item.attempt,
    reference: item.step === 2 ? item.correct : "",
    last: null,
  };
}

function advance(state: RoundState, finished: FinishedItem): RoundState {
  const withFinished = { ...state, finished: [...state.finished, finished], last: null };
  const nextIndex = state.index + 1;
  if (nextIndex >= state.items.length) {
    return { ...withFinished, phase: "summary" };
  }
  return startItem(withFinished, nextIndex);
}

function finishedKind(item: RoundItem, response: AnswerResponse): FinishedKind {
  const result = response.result;
  if (!result || result.outcome === "failed") {
    return "back";
  }
  if (result.outcome === "second_try") {
    return "repeat";
  }
  return result.mastered && !item.mastered ? "mastered" : "advanced";
}

/**
 * Máquina de estados da rodada de revisão: tudo o que a tela decide fica aqui, sem rede nem
 * gravação, para ser testado como função pura. O servidor manda na etapa e na tentativa, e o
 * reducer só as guarda: o que ele recebe em `next` vira o estado da próxima resposta.
 */
export function roundReducer(state: RoundState, event: RoundEvent): RoundState {
  switch (event.type) {
    case "loaded":
      if (event.items.length === 0) {
        return { ...INITIAL_ROUND_STATE, phase: "empty" };
      }
      return startItem({ ...INITIAL_ROUND_STATE, items: event.items }, 0);

    case "recordingStarted":
      return CAN_RECORD.includes(state.phase) ? { ...state, phase: "recording" } : state;

    case "micDenied":
      return state.phase === "recording" || state.phase === "idle"
        ? { ...state, phase: "mic_denied" }
        : state;

    case "tooShort":
      return state.phase === "recording" ? { ...state, phase: "not_heard" } : state;

    case "submitted":
      return state.phase === "recording" ? { ...state, phase: "analyzing" } : state;

    case "answered": {
      if (state.phase !== "analyzing") {
        return state;
      }
      if (event.response.status === "not_heard") {
        return { ...state, phase: "not_heard" };
      }
      const revealed = event.response.revealed_correct;
      return {
        ...state,
        phase: "result",
        last: event.response,
        reference: state.step === 1 && revealed ? revealed : state.reference,
      };
    }

    case "failed":
      return state.phase === "analyzing" ? { ...state, phase: "unavailable" } : state;

    case "tooMany":
      return state.phase === "analyzing" ? { ...state, phase: "too_many" } : state;

    case "retry":
      return state.phase === "unavailable" ? { ...state, phase: "analyzing" } : state;

    case "continue": {
      const response = state.last;
      if (state.phase !== "result" || !response) {
        return state;
      }
      if (response.next) {
        return {
          ...state,
          phase: "idle",
          step: response.next.step,
          attempt: response.next.attempt,
          last: null,
        };
      }
      const item = state.items[state.index];
      return advance(state, {
        item,
        kind: finishedKind(item, response),
        intervalDays: response.result?.interval_days ?? null,
      });
    }

    case "askDiscard":
      return CAN_DISCARD.includes(state.phase)
        ? { ...state, phase: "confirm_discard", phaseBeforeDiscard: state.phase }
        : state;

    case "cancelDiscard":
      return state.phase === "confirm_discard" ? { ...state, phase: state.phaseBeforeDiscard } : state;

    case "discarded":
      if (state.phase !== "confirm_discard") {
        return state;
      }
      return advance(state, {
        item: state.items[state.index],
        kind: "discarded",
        intervalDays: null,
      });
  }
}

/** Veredito mostrado depois de uma resposta: certo, primeiro erro ou erro na última tentativa. */
export function verdictLabel(response: AnswerResponse, attempt: Attempt): string {
  if (response.correct) {
    return "Certo";
  }
  return attempt === 1 ? "Ainda não" : "Não foi desta vez";
}

/** Rótulo da ação que segue o resultado: tentar de novo, continuar, próximo item ou resumo. */
export function resultActionLabel(state: RoundState): string {
  const response = state.last;
  if (response?.next) {
    return response.next.step === state.step ? "Tentar de novo" : "Continuar";
  }
  return state.index === state.items.length - 1 ? "Ver resumo" : "Próximo item";
}

export interface RoundCounts {
  advanced: number;
  repeat: number;
  back: number;
  mastered: number;
  discarded: number;
}

/** Quantos itens da rodada caíram em cada saída, para o resumo do fim. */
export function roundCounts(finished: FinishedItem[]): RoundCounts {
  const counts: RoundCounts = { advanced: 0, repeat: 0, back: 0, mastered: 0, discarded: 0 };
  for (const entry of finished) {
    counts[entry.kind] += 1;
  }
  return counts;
}

/** Quando o item volta, como a lista do resumo o mostra. */
export function comesBackLabel(entry: FinishedItem): string {
  if (entry.kind === "discarded") {
    return "Descartado";
  }
  if (entry.kind === "mastered") {
    return "✓ Dominado";
  }
  return entry.intervalDays === 1 ? "volta amanhã" : `volta em ${entry.intervalDays} dias`;
}
