import { describe, expect, it } from "vitest";

import type { AnswerResponse, RoundItem } from "../api/reviewRound";
import {
  INITIAL_ROUND_STATE,
  comesBackLabel,
  resultActionLabel,
  roundCounts,
  roundReducer,
  verdictLabel,
  type RoundEvent,
  type RoundState,
} from "./reviewRound";

function item(id: number, overrides: Partial<RoundItem> = {}): RoundItem {
  return {
    id,
    said: `disse ${id}`,
    scenario_title: "Entrevista",
    occurred_at: "2026-10-04T14:00:00Z",
    interval_days: 3,
    mastered: false,
    step: 1,
    attempt: 1,
    correct: `correto ${id}`,
    ...overrides,
  };
}

function judged(overrides: Partial<AnswerResponse> = {}): AnswerResponse {
  return {
    status: "judged",
    answer_id: 7,
    heard: "I worked there yesterday",
    correct: true,
    feedback: "Certo.",
    revealed_correct: "",
    next: { step: 2, attempt: 1 },
    result: null,
    ...overrides,
  };
}

function run(events: RoundEvent[], from: RoundState = INITIAL_ROUND_STATE): RoundState {
  return events.reduce(roundReducer, from);
}

function answer(response: AnswerResponse): RoundEvent[] {
  return [
    { type: "recordingStarted" },
    { type: "submitted" },
    { type: "answered", response },
  ];
}

const loaded = (...items: RoundItem[]): RoundEvent => ({ type: "loaded", items });

describe("carregar a rodada", () => {
  it("sem itens, o estado é vazio", () => {
    expect(run([loaded()]).phase).toBe("empty");
  });

  it("começa no primeiro item, na etapa e tentativa que o servidor mandou", () => {
    const state = run([loaded(item(1, { step: 2, attempt: 2, correct: "forma correta" }))]);

    expect(state).toMatchObject({ phase: "idle", index: 0, step: 2, attempt: 2 });
    expect(state.reference).toBe("forma correta");
  });

  it("um item novo, na etapa 1, não tem referência", () => {
    expect(run([loaded(item(1, { correct: "forma correta" }))]).reference).toBe("");
  });
});

describe("gravar e responder", () => {
  it("segue gravar, analisar e mostrar o resultado", () => {
    const states = [
      loaded(item(1)),
      { type: "recordingStarted" },
      { type: "submitted" },
      { type: "answered", response: judged() },
    ] as RoundEvent[];
    const phases: string[] = [];
    states.reduce((state, event) => {
      const next = roundReducer(state, event);
      phases.push(next.phase);
      return next;
    }, INITIAL_ROUND_STATE);

    expect(phases).toEqual(["idle", "recording", "analyzing", "result"]);
  });

  it("um toque curto demais vira 'não consegui ouvir' e mantém a tentativa", () => {
    const state = run([loaded(item(1)), { type: "recordingStarted" }, { type: "tooShort" }]);

    expect(state).toMatchObject({ phase: "not_heard", step: 1, attempt: 1 });
  });

  it("depois de 'não consegui ouvir', dá para gravar de novo", () => {
    const state = run([
      loaded(item(1)),
      { type: "recordingStarted" },
      { type: "tooShort" },
      { type: "recordingStarted" },
    ]);

    expect(state.phase).toBe("recording");
  });

  it("uma fala sem texto, devolvida pelo servidor, também mantém a tentativa", () => {
    const silent = judged({ status: "not_heard", answer_id: null, next: null, correct: null });

    const state = run([loaded(item(1)), ...answer(silent)]);

    expect(state).toMatchObject({ phase: "not_heard", step: 1, attempt: 1, last: null });
  });

  it("negar o microfone mostra o aviso e permite tentar de novo", () => {
    const denied = run([loaded(item(1)), { type: "micDenied" }]);

    expect(denied.phase).toBe("mic_denied");
    expect(roundReducer(denied, { type: "recordingStarted" }).phase).toBe("recording");
  });

  it("não deixa gravar enquanto analisa", () => {
    const state = run([loaded(item(1)), { type: "recordingStarted" }, { type: "submitted" }]);

    expect(roundReducer(state, { type: "recordingStarted" }).phase).toBe("analyzing");
  });
});

describe("falha do serviço", () => {
  const analyzing = () =>
    run([loaded(item(1)), { type: "recordingStarted" }, { type: "submitted" }]);

  it("mostra a falha e permite reenviar a mesma gravação", () => {
    const failed = roundReducer(analyzing(), { type: "failed" });

    expect(failed.phase).toBe("unavailable");
    expect(roundReducer(failed, { type: "retry" }).phase).toBe("analyzing");
  });

  it("a falha não muda a etapa nem a tentativa", () => {
    const failed = roundReducer(analyzing(), { type: "failed" });

    expect(failed).toMatchObject({ step: 1, attempt: 1 });
  });
});

describe("continuar depois do resultado", () => {
  it("acerto na etapa 1 vai para a etapa 2 com a forma correta como referência", () => {
    const response = judged({ revealed_correct: "I worked there yesterday." });

    const state = run([loaded(item(1)), ...answer(response), { type: "continue" }]);

    expect(state).toMatchObject({ phase: "idle", step: 2, attempt: 1 });
    expect(state.reference).toBe("I worked there yesterday.");
    expect(state.last).toBeNull();
  });

  it("um primeiro erro continua na etapa, na segunda tentativa", () => {
    const response = judged({ correct: false, next: { step: 1, attempt: 2 } });

    const state = run([loaded(item(1)), ...answer(response), { type: "continue" }]);

    expect(state).toMatchObject({ phase: "idle", step: 1, attempt: 2, reference: "" });
  });

  it("terminar o item passa para o próximo", () => {
    const finish = judged({
      next: null,
      result: { outcome: "first_try", interval_days: 7, due_on: "2026-10-15", mastered: false },
    });

    const state = run([
      loaded(item(1), item(2)),
      ...answer(finish),
      { type: "continue" },
    ]);

    expect(state).toMatchObject({ phase: "idle", index: 1, step: 1, attempt: 1 });
    expect(state.finished).toHaveLength(1);
    expect(state.finished[0]).toMatchObject({ kind: "advanced", intervalDays: 7 });
  });

  it("terminar o último item abre o resumo", () => {
    const finish = judged({
      next: null,
      result: { outcome: "failed", interval_days: 1, due_on: "2026-10-09", mastered: false },
    });

    const state = run([loaded(item(1)), ...answer(finish), { type: "continue" }]);

    expect(state.phase).toBe("summary");
    expect(state.finished[0].kind).toBe("back");
  });

  it("não continua sem um resultado para continuar", () => {
    const state = run([loaded(item(1))]);

    expect(roundReducer(state, { type: "continue" })).toBe(state);
  });
});

describe("como cada saída do item aparece no resumo", () => {
  const resultOf = (outcome: "first_try" | "second_try" | "failed", mastered = false) =>
    judged({
      next: null,
      result: { outcome, interval_days: 14, due_on: "2026-10-22", mastered },
    });

  function kindAfter(response: AnswerResponse, overrides: Partial<RoundItem> = {}) {
    return run([loaded(item(1, overrides)), ...answer(response), { type: "continue" }])
      .finished[0].kind;
  }

  it("acerto de primeira avança", () => {
    expect(kindAfter(resultOf("first_try"))).toBe("advanced");
  });

  it("acerto na segunda tentativa repete o intervalo", () => {
    expect(kindAfter(resultOf("second_try"))).toBe("repeat");
  });

  it("erro volta amanhã", () => {
    expect(kindAfter(resultOf("failed"))).toBe("back");
  });

  it("acertar de primeira e ficar dominado conta como dominado", () => {
    expect(kindAfter(resultOf("first_try", true))).toBe("mastered");
  });

  it("um item que já era dominado e avançou não conta como recém-dominado", () => {
    expect(kindAfter(resultOf("first_try", true), { mastered: true })).toBe("advanced");
  });
});

describe("Não disse isso", () => {
  it("pede confirmação e, ao cancelar, volta para onde estava", () => {
    const asked = run([loaded(item(1)), { type: "askDiscard" }]);

    expect(asked.phase).toBe("confirm_discard");
    expect(roundReducer(asked, { type: "cancelDiscard" }).phase).toBe("idle");
  });

  it("cancelar volta ao resultado quando foi pedido nele", () => {
    const asked = run([loaded(item(1)), ...answer(judged()), { type: "askDiscard" }]);

    expect(roundReducer(asked, { type: "cancelDiscard" }).phase).toBe("result");
  });

  it("não deixa descartar enquanto grava ou analisa", () => {
    const recording = run([loaded(item(1)), { type: "recordingStarted" }]);

    expect(roundReducer(recording, { type: "askDiscard" })).toBe(recording);
  });

  it("confirmar arquiva o item e segue para o próximo", () => {
    const state = run([
      loaded(item(1), item(2)),
      { type: "askDiscard" },
      { type: "discarded" },
    ]);

    expect(state).toMatchObject({ phase: "idle", index: 1 });
    expect(state.finished[0]).toMatchObject({ kind: "discarded", intervalDays: null });
  });

  it("descartar o último item abre o resumo", () => {
    const state = run([loaded(item(1)), { type: "askDiscard" }, { type: "discarded" }]);

    expect(state.phase).toBe("summary");
  });
});

describe("rótulos", () => {
  it("o veredito depende de acertar e da tentativa", () => {
    expect(verdictLabel(judged({ correct: true }), 1)).toBe("Certo");
    expect(verdictLabel(judged({ correct: false }), 1)).toBe("Ainda não");
    expect(verdictLabel(judged({ correct: false }), 2)).toBe("Não foi desta vez");
  });

  it("a ação depois do resultado", () => {
    const base = run([loaded(item(1), item(2))]);
    const retry = { ...base, last: judged({ correct: false, next: { step: 1, attempt: 2 } }) };
    const toStepTwo = { ...base, last: judged() };
    const lastItem = { ...base, index: 1, last: judged({ next: null }) };
    const middleItem = { ...base, last: judged({ next: null }) };

    expect(resultActionLabel(retry)).toBe("Tentar de novo");
    expect(resultActionLabel(toStepTwo)).toBe("Continuar");
    expect(resultActionLabel(middleItem)).toBe("Próximo item");
    expect(resultActionLabel(lastItem)).toBe("Ver resumo");
  });

  it("conta cada saída e diz quando cada item volta", () => {
    const finished = [
      { item: item(1), kind: "advanced" as const, intervalDays: 7 },
      { item: item(2), kind: "back" as const, intervalDays: 1 },
      { item: item(3), kind: "mastered" as const, intervalDays: 60 },
      { item: item(4), kind: "discarded" as const, intervalDays: null },
      { item: item(5), kind: "repeat" as const, intervalDays: 3 },
    ];

    expect(roundCounts(finished)).toEqual({
      advanced: 1,
      repeat: 1,
      back: 1,
      mastered: 1,
      discarded: 1,
    });
    expect(finished.map(comesBackLabel)).toEqual([
      "volta em 7 dias",
      "volta amanhã",
      "✓ Dominado",
      "Descartado",
      "volta em 3 dias",
    ]);
  });
});
