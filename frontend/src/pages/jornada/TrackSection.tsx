import type { TrackState } from "../../api/journey";
import { ScenarioRow } from "./ScenarioRow";

interface TrackSectionProps {
  track: TrackState;
}

/** Uma trilha inteira, com a barra de progresso e os cenarios dentro dela. */
export function TrackSection({ track }: TrackSectionProps) {
  const pct = track.possible_levels > 0 ? Math.round((track.approved_levels / track.possible_levels) * 100) : 0;

  return (
    <section className="mb-12">
      <div className="mb-4 flex items-center gap-3">
        <span
          className={`text-aux font-semibold uppercase tracking-wide ${
            track.unlocked ? "text-ink" : "text-ink-disabled"
          }`}
        >
          {track.title}
        </span>
        {track.unlocked && !track.completed && (
          <span className="rounded-pill bg-brand-soft px-2.5 py-0.5 text-[11px] font-semibold text-brand-strong">
            em andamento
          </span>
        )}
        <div className="flex-1" />
        <span className="text-score font-medium text-ink-muted">
          {track.approved_levels} de {track.possible_levels}
        </span>
      </div>

      <div className="mb-5 h-1 overflow-hidden rounded-pill bg-line">
        <div className="h-full rounded-pill bg-brand" style={{ width: `${pct}%` }} />
      </div>

      {!track.unlocked && (
        <p className="mb-4 text-aux text-ink-muted">Conclua as trilhas anteriores para desbloquear</p>
      )}

      <div className="flex flex-col gap-3">
        {track.scenario_states.map((scenario) => (
          <ScenarioRow key={scenario.slug} trackTitle={track.title} scenario={scenario} />
        ))}
      </div>
    </section>
  );
}
