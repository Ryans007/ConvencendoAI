import { describe, expect, it } from "vitest";

import type { LevelState, ScenarioState } from "../../api/journey";
import { castLine, initialLevelOrder, levelDash, levelStatus, scenarioMark } from "./journeyView";

interface LevelOptions {
  approved?: boolean;
  tried?: boolean;
  cooldownSeconds?: number | null;
}

function level(order: number, options: LevelOptions = {}): LevelState {
  const { approved = false, tried = approved, cooldownSeconds = null } = options;
  return {
    order,
    name: `Nível ${order}`,
    expected_cefr: "A2-B1",
    expected_production: "Produção esperada.",
    approved,
    available: cooldownSeconds === null,
    cooldown_remaining_seconds: cooldownSeconds,
    last_attempt: tried
      ? { id: order, final_score: 70, passed: approved, completed_at: "2026-10-07T12:00:00Z" }
      : null,
  };
}

function scenario(levels: LevelState[], overrides: Partial<ScenarioState> = {}): ScenarioState {
  return {
    slug: "entrevista",
    title: "Entrevista",
    order: 1,
    completed: false,
    unlocked: true,
    cast: [],
    level_states: levels,
    ...overrides,
  };
}

describe("scenarioMark", () => {
  it("é bloqueado quando o cenário não está liberado", () => {
    expect(scenarioMark(scenario([level(1)], { unlocked: false }))).toBe("locked");
  });

  it("é aprovado quando o cenário está concluído, mesmo com outros níveis tentados", () => {
    const marked = scenario([level(1, { approved: true }), level(2, { tried: true })], {
      completed: true,
    });

    expect(scenarioMark(marked)).toBe("passed");
  });

  it("é tentou e não passou quando há tentativa e nenhuma aprovação", () => {
    expect(scenarioMark(scenario([level(1, { tried: true }), level(2)]))).toBe("attempted");
  });

  it("é disponível quando está liberado e nunca foi tentado", () => {
    expect(scenarioMark(scenario([level(1), level(2)]))).toBe("available");
  });
});

describe("initialLevelOrder", () => {
  it("é o primeiro nível ainda não aprovado", () => {
    const levels = [level(1, { approved: true }), level(2), level(3)];

    expect(initialLevelOrder(scenario(levels))).toBe(2);
  });

  it("não pula um nível não aprovado só porque um posterior foi aprovado", () => {
    const levels = [level(1), level(2, { approved: true }), level(3)];

    expect(initialLevelOrder(scenario(levels))).toBe(1);
  });

  it("é o último quando todos estão aprovados", () => {
    const levels = [1, 2, 3].map((order) => level(order, { approved: true }));

    expect(initialLevelOrder(scenario(levels))).toBe(3);
  });
});

describe("levelDash", () => {
  it("distingue aprovado, tentado e nunca tentado", () => {
    expect(levelDash(level(1, { approved: true }))).toBe("approved");
    expect(levelDash(level(1, { tried: true }))).toBe("attempted");
    expect(levelDash(level(1))).toBe("untried");
  });
});

describe("levelStatus", () => {
  it("nível nunca tentado: Disponível e Começar", () => {
    expect(levelStatus(level(1))).toEqual({
      label: "Disponível",
      action: "Começar",
      cooldown: null,
    });
  });

  it("nível aprovado: Aprovado e Refazer", () => {
    expect(levelStatus(level(1, { approved: true }))).toEqual({
      label: "Aprovado",
      action: "Refazer",
      cooldown: null,
    });
  });

  it("nível reprovado em cooldown: Não atingiu a nota, com o tempo para liberar", () => {
    expect(levelStatus(level(1, { tried: true, cooldownSeconds: 6 * 3600 }))).toEqual({
      label: "Não atingiu a nota",
      action: "Refazer",
      cooldown: "Libera em 6h",
    });
  });
});

describe("castLine", () => {
  it("junta nome e função, na ordem recebida", () => {
    const cast = [
      { name: "Rachel", scene_function: "recrutadora de RH" },
      { name: "Tom", scene_function: "tech lead do time de backend" },
    ];

    expect(castLine(cast)).toBe(
      "Rachel (recrutadora de RH) · Tom (tech lead do time de backend)",
    );
  });

  it("é vazio para um cenário sem elenco", () => {
    expect(castLine([])).toBe("");
  });
});
