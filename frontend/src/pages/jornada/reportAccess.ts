import type { LevelState, ScenarioState } from "../../api/journey";
import type { ReportContext } from "../relatorio/reportContext";

export interface ReportAccess {
  to: string;
  state: { reportContext: ReportContext };
  ariaLabel: string;
}

/**
 * Destino do acesso "Ver último relatório" de um nível da jornada, ou `null` quando o
 * aluno nunca concluiu uma tentativa nele. O contexto leva trilha, título do cenário e o
 * rótulo do nível no mesmo formato do briefing ("nome do nível, nível CEFR"), para o
 * cabeçalho do relatório sair completo, como sai ao fim de uma sessão. O rótulo de
 * acessibilidade inclui cenário e nível porque uma linha da jornada tem três links iguais.
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
    ariaLabel: `Ver último relatório: ${scenario.title}, ${level.name}`,
  };
}
