import { describe, expect, it } from "vitest";

import type { AttemptReport, SpeechMetrics } from "../../api/attemptReport";
import { dimensionMeasures, scoringExplanation } from "./reportText";

const LEVEL_THREE_METRICS: SpeechMetrics = {
  reaction_seconds: 4,
  words_per_minute: 92.4,
  long_pauses_per_100_words: 3.12,
  lexical_diversity: 0.62,
  lexical_range: 0.06,
};

function report(overrides: Partial<AttemptReport> = {}): AttemptReport {
  return {
    id: 1,
    scenario: "negociar-prazo",
    level: 3,
    final_score: 74,
    passed: true,
    feedback: "Bom trabalho.",
    completed_at: "2026-10-24T12:00:00Z",
    hints_enabled: false,
    hints_used: 0,
    score_breakdowns: [
      { dimension: "objective", value: 23, weight: 30, comment: "" },
      { dimension: "fluency", value: 11, weight: 15, comment: "" },
      { dimension: "vocabulary", value: 7, weight: 10, comment: "" },
      { dimension: "grammar", value: 10, weight: 15, comment: "" },
      { dimension: "pragmatics", value: 12, weight: 15, comment: "" },
      { dimension: "autonomy", value: 4, weight: 5, comment: "" },
    ],
    criteria: [],
    mistakes: [],
    speech_metrics: null,
    scoring: { passing_score: 70, fluency: null, vocabulary: null },
    ...overrides,
  };
}

describe("pages/relatorio/reportText", () => {
  it("mostra as medidas de fluencia em portugues", () => {
    expect(dimensionMeasures("fluency", LEVEL_THREE_METRICS)).toEqual([
      "Tempo para começar a responder: 4,0 s",
      "Velocidade: 92 palavras por minuto",
      "Pausas longas: 3,1 a cada 100 palavras",
    ]);
  });

  it("mostra as medidas de vocabulario em porcentagem", () => {
    expect(dimensionMeasures("vocabulary", LEVEL_THREE_METRICS)).toEqual([
      "Variedade de palavras: 62%",
      "Palavras menos comuns: 6%",
    ]);
  });

  it("no nivel 1 a fluencia mostra so o tempo de reacao", () => {
    const levelOne: SpeechMetrics = {
      reaction_seconds: 5.25,
      words_per_minute: null,
      long_pauses_per_100_words: null,
      lexical_diversity: null,
      lexical_range: null,
    };

    expect(dimensionMeasures("fluency", levelOne)).toEqual([
      "Tempo para começar a responder: 5,3 s",
    ]);
    expect(dimensionMeasures("vocabulary", levelOne)).toEqual([]);
  });

  it("sem medidas, nenhuma dimensao mostra nada", () => {
    expect(dimensionMeasures("fluency", null)).toEqual([]);
    expect(dimensionMeasures("grammar", LEVEL_THREE_METRICS)).toEqual([]);
  });

  it("a explicacao soma os pontos e os pesos da tentativa", () => {
    const explanation = scoringExplanation(report());

    expect(explanation.weights[1]).toEqual({ label: "Fluência", value: 11, weight: 15 });
    expect(explanation.achieved).toBe(67);
    expect(explanation.possible).toBe(90);
    expect(explanation.finalScore).toBe(74);
    expect(explanation.passingScore).toBe(70);
  });

  it("uma tentativa sem medidas nao explica fluencia nem vocabulario medidos", () => {
    const explanation = scoringExplanation(report());

    expect(explanation.fluency).toBeNull();
    expect(explanation.vocabulary).toBeNull();
  });

  it("explica as proporcoes da fluencia e do vocabulario medidos", () => {
    const explanation = scoringExplanation(
      report({
        scoring: {
          passing_score: 70,
          fluency: { measured_share: 0.7, reaction_share: 0.4, speed_share: 0.4, pauses_share: 0.2 },
          vocabulary: { judged_share: 0.5, diversity_share: 0.25, range_share: 0.25 },
        },
      }),
    );

    expect(explanation.fluency).toBe(
      "Fluência: 70% vem das medidas da sua fala (tempo para começar a responder 40%, " +
        "velocidade 40%, pausas longas 20%) e 30% do avaliador, que olha se a fala ficou clara.",
    );
    expect(explanation.vocabulary).toBe(
      "Vocabulário: 50% do avaliador, que olha a precisão das palavras, 25% da variedade de " +
        "palavras, 25% das palavras menos comuns.",
    );
  });

  it("no nivel 1 a fluencia medida e so o tempo de reacao", () => {
    const explanation = scoringExplanation(
      report({
        scoring: {
          passing_score: 70,
          fluency: { measured_share: 0.7, reaction_share: 1, speed_share: 0, pauses_share: 0 },
          vocabulary: null,
        },
      }),
    );

    expect(explanation.fluency).toBe(
      "Fluência: 70% vem das medidas da sua fala (tempo para começar a responder) e 30% do " +
        "avaliador, que olha se a fala ficou clara.",
    );
  });
});
