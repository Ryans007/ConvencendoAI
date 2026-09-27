import { useNavigate } from "react-router-dom";

import type { LevelState, ScenarioState } from "../../api/journey";
import { formatCooldown } from "./scenarioAction";

interface ScenarioRowProps {
  trackTitle: string;
  scenario: ScenarioState;
}

interface LevelButtonProps {
  scenarioSlug: string;
  trackTitle: string;
  clickable: boolean;
  level: LevelState;
}

function LevelButton({ scenarioSlug, trackTitle, clickable, level }: LevelButtonProps) {
  const navigate = useNavigate();

  const label = level.approved
    ? "Aprovado"
    : level.available
      ? "Disponível"
      : level.cooldown_remaining_seconds !== null
        ? formatCooldown(level.cooldown_remaining_seconds)
        : "Bloqueado";

  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={() =>
        navigate(`/cenario/${scenarioSlug}/${level.order}`, { state: { trackTitle } })
      }
      className={`flex flex-1 flex-col items-start gap-1 rounded-[10px] border px-3 py-2.5 text-left ${
        clickable
          ? "cursor-pointer border-brand-line bg-brand-soft hover:border-brand-line-strong"
          : "cursor-default border-line bg-surface-muted"
      }`}
    >
      <span className={`text-aux font-medium ${clickable ? "text-ink" : "text-ink-disabled"}`}>
        {level.name}
      </span>
      <span className={`text-aux ${level.approved ? "text-brand-strong" : "text-ink-muted"}`}>
        {label}
      </span>
    </button>
  );
}

/** Um cenario dentro de uma trilha, com os tres niveis independentes para escolher. */
export function ScenarioRow({ trackTitle, scenario }: ScenarioRowProps) {
  const approvedCount = scenario.level_states.filter((level) => level.approved).length;

  return (
    <div
      className={`rounded-card border border-line bg-surface p-5 shadow-card ${
        !scenario.unlocked ? "opacity-70" : ""
      }`}
    >
      <div className="mb-3 flex items-center justify-between gap-4">
        <span className={`text-scenario font-medium ${scenario.unlocked ? "text-ink" : "text-ink-disabled"}`}>
          {scenario.title}
        </span>
        <div className="flex items-center gap-2">
          {scenario.completed && (
            <span className="text-aux font-medium text-brand-strong">Aprovado</span>
          )}
          <span className="text-aux text-ink-muted">{approvedCount} de {scenario.level_states.length}</span>
        </div>
      </div>

      {!scenario.unlocked ? (
        <p className="text-aux text-ink-muted">Conclua o cenário anterior para desbloquear.</p>
      ) : (
        <div className="flex gap-2">
          {scenario.level_states.map((level) => (
            <LevelButton
              key={level.order}
              scenarioSlug={scenario.slug}
              trackTitle={trackTitle}
              clickable={level.available}
              level={level}
            />
          ))}
        </div>
      )}
    </div>
  );
}
