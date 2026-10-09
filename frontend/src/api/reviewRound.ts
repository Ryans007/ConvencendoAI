import { get, getBlob, post, postForm } from "./client";

export type Step = 1 | 2;
export type Attempt = 1 | 2;

/** Um item da rodada, como a tela do item o mostra. */
export interface RoundItem {
  id: number;
  said: string;
  scenario_title: string;
  occurred_at: string;
  interval_days: number;
  mastered: boolean;
  step: Step;
  attempt: Attempt;
  correct: string;
}

export interface RoundPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: RoundItem[];
}

export interface NextStep {
  step: Step;
  attempt: Attempt;
}

export type ReviewOutcome = "first_try" | "second_try" | "failed";

/** O que a revisão terminada fez com o item no calendário. */
export interface ItemResult {
  outcome: ReviewOutcome;
  interval_days: number;
  due_on: string;
  mastered: boolean;
}

/** O veredito de uma resposta e para onde o item vai: a próxima etapa ou o resultado. */
export interface AnswerResponse {
  status: "judged" | "not_heard";
  answer_id: number | null;
  heard: string;
  correct: boolean | null;
  feedback: string;
  revealed_correct: string;
  next: NextStep | null;
  result: ItemResult | null;
}

/** Chamada de `GET /review/round/`: a primeira página dos itens vencidos, que é a rodada. */
export function fetchRound(signal?: AbortSignal): Promise<RoundPage> {
  return get<RoundPage>("/review/round/", { signal });
}

/** Chamada de `POST /review/items/<id>/answers/`: envia a gravação da resposta falada. */
export function sendAnswer(itemId: number, audio: Blob): Promise<AnswerResponse> {
  const form = new FormData();
  form.append("audio", audio, "answer.webm");
  return postForm<AnswerResponse>(`/review/items/${itemId}/answers/`, form);
}

/** Chamada de `POST /review/items/<id>/discard/`: o aluno disse "Não disse isso". */
export function discardItem(itemId: number): Promise<void> {
  return post<void>(`/review/items/${itemId}/discard/`, undefined);
}

/** Chamada de `GET /review/answers/<id>/audio/`: o áudio da forma correta revelada. */
export function fetchAnswerAudio(answerId: number): Promise<Blob> {
  return getBlob(`/review/answers/${answerId}/audio/`);
}
