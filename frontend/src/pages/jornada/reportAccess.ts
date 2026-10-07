import type { LevelState, ScenarioState } from "../../api/journey";
import type { ReportContext } from "../relatorio/reportContext";

export interface ReportAccess {
  to: string;
  state: { reportContext: ReportContext };
  ariaLabel: string;
}

/**
 * Destino da nota de um nível da jornada, que abre o último relatório, ou `null` quando o
 * aluno nunca concluiu uma tentativa nele. O contexto leva trilha, título do cenário e o
 * rótulo do nível no mesmo formato do briefing ("nome do nível, nível CEFR"), para o
 * cabeçalho do relatório sair completo, como sai ao fim de uma sessão. O rótulo de
 * acessibilidade inclui cenário e nível porque a nota sozinha não diz o que abre.
 */
export function reportAccess(
  trackTitle: string,
  scenario: ScenarioState,
  level: LevelState,
): ReportAccess | null {
  if (level.last_attempt === null) {
    return null;
  }
  return {
    to: `/relatorio/${level.last_attempt.id}`,
    state: {
      reportContext: {
        scenarioTitle: scenario.title,
        levelLabel: `${level.name}, nível ${level.expected_cefr}`,
        trackTitle,
      },
    },
    ariaLabel: `Abrir último relatório: ${scenario.title}, ${level.name}`,
  };
}
