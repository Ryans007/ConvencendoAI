import { describe, expect, it } from "vitest";

import type { LevelState, ScenarioState } from "../../api/journey";
import {
  castLine,
  initialLevelOrder,
  latestAttempt,
  levelDash,
  levelStatus,
  scenarioCardKey,
  scenarioMark,
} from "./journeyView";

interface LevelOptions {
  approved?: boolean;
  tried?: boolean;
  cooldownSeconds?: number | null;
  attemptId?: number;
  completedAt?: string;
}

function level(order: number, options: LevelOptions = {}): LevelState {
  const {
    approved = false,
    tried = approved,
    cooldownSeconds = null,
    attemptId = order,
    completedAt = "2026-10-07T12:00:00Z",
  } = options;
  return {
    order,
    name: `Nível ${order}`,
    expected_cefr: "A2-B1",
    expected_production: "Produção esperada.",
    approved,
    available: cooldownSeconds === null,
    cooldown_remaining_seconds: cooldownSeconds,
    last_attempt: tried
      ? { id: attemptId, final_score: 70, passed: approved, completed_at: completedAt }
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

describe("latestAttempt", () => {
  it("é a tentativa de um nível posterior quando só ele foi feito", () => {
    const levels = [level(1), level(2), level(3, { tried: true, attemptId: 7 })];

    expect(latestAttempt(scenario(levels))).toMatchObject({ levelOrder: 3, attempt: { id: 7 } });
  });

  it("é a de um nível anterior quando ela foi concluída depois", () => {
    const levels = [
      level(1, { tried: true, attemptId: 9, completedAt: "2026-11-12T15:00:00Z" }),
      level(2),
      level(3, { approved: true, attemptId: 6, completedAt: "2026-11-08T19:08:59Z" }),
    ];

    expect(latestAttempt(scenario(levels))?.levelOrder).toBe(1);
  });

  it("compara instantes, e não o texto, quando os fusos são diferentes", () => {
    const levels = [
      level(1, { tried: true, attemptId: 1, completedAt: "2026-11-12T11:30:00-03:00" }),
      level(2, { tried: true, attemptId: 2, completedAt: "2026-11-12T14:00:00Z" }),
    ];

    expect(latestAttempt(scenario(levels))?.levelOrder).toBe(1);
  });

  it("desempata pelo id quando a conclusão é no mesmo instante", () => {
    const levels = [
      level(1, { tried: true, attemptId: 5 }),
      level(2, { tried: true, attemptId: 4 }),
    ];

    expect(latestAttempt(scenario(levels))?.levelOrder).toBe(1);
  });

  it("é nula quando o aluno nunca concluiu uma tentativa no cenário", () => {
    expect(latestAttempt(scenario([level(1), level(2), level(3)]))).toBeNull();
  });
});

describe("initialLevelOrder", () => {
  it("é o nível da última sessão, reprovada, mesmo com níveis anteriores pendentes", () => {
    const levels = [level(1), level(2), level(3, { tried: true })];

    expect(initialLevelOrder(scenario(levels))).toBe(3);
  });

  it("é o nível da última sessão quando ela foi aprovada", () => {
    const levels = [level(1), level(2), level(3, { approved: true })];

    expect(initialLevelOrder(scenario(levels))).toBe(3);
  });

  it("é um nível anterior quando a tentativa mais recente foi nele", () => {
    const levels = [
      level(1, { tried: true, attemptId: 9, completedAt: "2026-11-12T15:00:00Z" }),
      level(2),
      level(3, { approved: true, attemptId: 6, completedAt: "2026-11-08T19:08:59Z" }),
    ];

    expect(initialLevelOrder(scenario(levels))).toBe(1);
  });

  it("é o primeiro nível quando o cenário nunca foi tentado", () => {
    expect(initialLevelOrder(scenario([level(1), level(2), level(3)]))).toBe(1);
  });

  it("sem tentativa concluída, é o primeiro nível ainda não aprovado", () => {
    const levels = [level(1, { approved: true, tried: false }), level(2), level(3)];

    expect(initialLevelOrder(scenario(levels))).toBe(2);
  });

  it("sem tentativa concluída, é o último quando todos estão aprovados", () => {
    const levels = [1, 2, 3].map((order) => level(order, { approved: true, tried: false }));

    expect(initialLevelOrder(scenario(levels))).toBe(3);
  });
});

describe("scenarioCardKey", () => {
  it("muda quando surge uma tentativa mais recente no cenário", () => {
    const before = scenario([level(1), level(2), level(3)]);
    const after = scenario([level(1), level(2), level(3, { tried: true, attemptId: 7 })]);

    expect(scenarioCardKey(after)).not.toBe(scenarioCardKey(before));
  });

  it("não muda quando a jornada é atualizada sem tentativa nova", () => {
    const levels = () => [level(1), level(2, { tried: true, attemptId: 4 })];

    expect(scenarioCardKey(scenario(levels()))).toBe(scenarioCardKey(scenario(levels())));
  });

  it("muda quando uma tentativa nova num nível substitui a anterior", () => {
    const before = scenario([level(1, { tried: true, attemptId: 4 })]);
    const after = scenario([
      level(1, { tried: true, attemptId: 8, completedAt: "2026-11-12T15:00:00Z" }),
    ]);

    expect(scenarioCardKey(after)).not.toBe(scenarioCardKey(before));
  });

  it("separa cenários diferentes sem tentativa", () => {
    const levels = [level(1)];

    expect(scenarioCardKey(scenario(levels, { slug: "a" }))).not.toBe(
      scenarioCardKey(scenario(levels, { slug: "b" })),
    );
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
