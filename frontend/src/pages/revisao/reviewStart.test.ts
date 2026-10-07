import { describe, expect, it } from "vitest";

import { nextReviewText, reviewStart } from "./reviewStart";

const TODAY = new Date(2026, 9, 7, 23, 30);

describe("reviewStart", () => {
  it("mostra quantos itens estão vencidos", () => {
    expect(reviewStart({ due: 3, next_due_on: "2026-10-09" }, TODAY)).toEqual({
      kind: "due",
      title: "Você tem 3 itens para revisar",
    });
  });

  it("usa o singular para um item", () => {
    expect(reviewStart({ due: 1, next_due_on: null }, TODAY)).toEqual({
      kind: "due",
      title: "Você tem 1 item para revisar",
    });
  });

  it("sem vencidos, mas com próximo vencimento, não há nada para hoje", () => {
    expect(reviewStart({ due: 0, next_due_on: "2026-10-08" }, TODAY)).toEqual({
      kind: "none",
      nextReview: "A próxima revisão é amanhã.",
    });
  });

  it("sem nenhum item, o estado é vazio", () => {
    expect(reviewStart({ due: 0, next_due_on: null }, TODAY)).toEqual({ kind: "empty" });
  });
});

describe("nextReviewText", () => {
  it("diz amanhã para o dia seguinte, mesmo no fim do dia", () => {
    expect(nextReviewText("2026-10-08", TODAY)).toBe("A próxima revisão é amanhã.");
  });

  it("diz em N dias para mais longe", () => {
    expect(nextReviewText("2026-10-12", TODAY)).toBe("A próxima revisão é em 5 dias.");
  });

  it("conta certo na virada do mês", () => {
    expect(nextReviewText("2026-11-02", TODAY)).toBe("A próxima revisão é em 26 dias.");
  });
});
