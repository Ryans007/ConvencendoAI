import { describe, expect, it } from "vitest";

import type { LevelState, ScenarioState } from "../../api/journey";
import { reportAccess } from "./reportAccess";

function levelState(lastAttemptId: number | null): LevelState {
  return {
    order: 1,
    name: "Ouvir",
    expected_cefr: "A1-A2",
    approved: false,
    available: false,
    cooldown_remaining_seconds: 7200,
    last_attempt:
      lastAttemptId === null
        ? null
        : { id: lastAttemptId, final_score: 64, passed: false, completed_at: "2026-10-04T12:00:00Z" },
  };
}

const scenario: ScenarioState = {
  slug: "entrevista-de-emprego",
  title: "Entrevista de emprego na TechCorp",
  order: 1,
  completed: false,
  unlocked: true,
  level_states: [],
};

describe("reportAccess", () => {
  it("não oferece acesso a um nível sem tentativa concluída", () => {
    expect(reportAccess("Carreira em TI", scenario, levelState(null))).toBeNull();
  });

  it("aponta para o relatório da última tentativa, mesmo com o nível em cooldown", () => {
    const access = reportAccess("Carreira em TI", scenario, levelState(42));

    expect(access?.to).toBe("/relatorio/42");
  });

  it("leva trilha, cenário e nível no mesmo formato do briefing", () => {
    const access = reportAccess("Carreira em TI", scenario, levelState(42));

    expect(access?.state.reportContext).toEqual({
      trackTitle: "Carreira em TI",
      scenarioTitle: "Entrevista de emprego na TechCorp",
      levelLabel: "Ouvir, nível A1-A2",
    });
  });

  it("identifica cenário e nível no rótulo de acessibilidade", () => {
    const access = reportAccess("Carreira em TI", scenario, levelState(42));

    expect(access?.ariaLabel).toBe(
      "Ver último relatório: Entrevista de emprego na TechCorp, Ouvir",
    );
  });
});
