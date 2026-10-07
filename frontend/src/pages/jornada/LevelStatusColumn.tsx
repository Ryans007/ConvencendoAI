import { Link, useNavigate } from "react-router-dom";

import type { LevelState, ScenarioState } from "../../api/journey";
import { levelStatus } from "./journeyView";
import { reportAccess } from "./reportAccess";

interface LevelStatusColumnProps {
  trackTitle: string;
  scenario: ScenarioState;
  level: LevelState;
}

/**
 * Coluna da direita do cartão: o estado do nível selecionado, a nota da última tentativa, que
 * abre o relatório, e a ação de começar ou refazer. A nota fica fora do botão da ação, então
 * continua acionável enquanto o nível está em cooldown e a ação, desabilitada.
 */
export function LevelStatusColumn({ trackTitle, scenario, level }: LevelStatusColumnProps) {
  const navigate = useNavigate();
  const status = levelStatus(level);
  const report = reportAccess(trackTitle, scenario, level);
  const waiting = status.cooldown !== null;

  return (
    <div className="flex flex-none flex-col items-start gap-2 sm:items-end">
      <div className="flex items-center gap-2">
        <span
          className={`text-aux font-medium ${level.approved ? "text-brand-strong" : "text-ink-muted"}`}
        >
          {status.label}
        </span>
        {report && level.last_attempt && (
          <Link
            to={report.to}
            state={report.state}
            aria-label={report.ariaLabel}
            className={`rounded-pill px-2.5 py-0.5 text-score font-semibold hover:underline ${
              level.last_attempt.passed ? "bg-brand-soft text-brand-strong" : "bg-line-strong text-ink"
            }`}
          >
            {level.last_attempt.final_score}
          </Link>
        )}
      </div>

      <button
        type="button"
        disabled={waiting}
        onClick={() => navigate(`/cenario/${scenario.slug}/${level.order}`, { state: { trackTitle } })}
        className={`rounded-pill px-5 py-2 text-score font-semibold ${
          waiting
            ? "cursor-not-allowed bg-line-strong text-ink-muted"
            : "cursor-pointer bg-brand text-white shadow-card-focus hover:bg-brand-strong"
        }`}
      >
        {status.cooldown ?? status.action}
      </button>
    </div>
  );
}
