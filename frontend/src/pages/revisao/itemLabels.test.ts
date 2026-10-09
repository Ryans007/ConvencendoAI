import { describe, expect, it } from "vitest";

import type { RoundItem } from "../../api/reviewRound";
import { ageLabel, filledBoxes, intervalLabel, originLabel } from "./itemLabels";

const NOW = new Date(2026, 9, 8, 0, 30);

function item(overrides: Partial<RoundItem> = {}): RoundItem {
  return {
    id: 1,
    said: "x",
    note: "",
    scenario_title: "Entrevista de emprego",
    occurred_at: new Date(2026, 9, 5, 23, 50).toISOString(),
    interval_days: 3,
    mastered: false,
    step: 1,
    attempt: 1,
    correct: "",
    ...overrides,
  };
}

describe("ageLabel", () => {
  it("conta dias de calendário, e não de 24 horas", () => {
    expect(ageLabel(new Date(2026, 9, 7, 23, 50).toISOString(), NOW)).toBe("ontem");
  });

  it("no mesmo dia, diz hoje", () => {
    expect(ageLabel(new Date(2026, 9, 8, 0, 5).toISOString(), NOW)).toBe("hoje");
  });

  it("para mais longe, diz há N dias", () => {
    expect(ageLabel(item().occurred_at, NOW)).toBe("há 3 dias");
  });
});

describe("originLabel", () => {
  it("junta a cena e quando foi", () => {
    expect(originLabel(item(), NOW)).toBe("Entrevista de emprego · há 3 dias");
  });
});

describe("intervalLabel", () => {
  it("diz o intervalo atual, no singular para 1 dia", () => {
    expect(intervalLabel(item({ interval_days: 3 }))).toBe("Intervalo de 3 dias");
    expect(intervalLabel(item({ interval_days: 1 }))).toBe("Intervalo de 1 dia");
  });

  it("diz Dominado para um item dominado", () => {
    expect(intervalLabel(item({ mastered: true, interval_days: 60 }))).toBe("Dominado");
  });
});

describe("filledBoxes", () => {
  it("preenche tantos tracinhos quanto a caixa", () => {
    expect([1, 3, 7, 14, 30].map((days) => filledBoxes(item({ interval_days: days })))).toEqual([
      1, 2, 3, 4, 5,
    ]);
  });

  it("um item dominado enche todos", () => {
    expect(filledBoxes(item({ mastered: true, interval_days: 120 }))).toBe(5);
  });
});
