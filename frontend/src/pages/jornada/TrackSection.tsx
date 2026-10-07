import type { TrackState } from "../../api/journey";
import { ScenarioCard } from "./ScenarioCard";
import { TimelineMark } from "./TimelineMark";
import { scenarioMark } from "./journeyView";

interface TrackSectionProps {
  track: TrackState;
}

/** Uma trilha inteira: a barra de progresso e os cenários numa linha do tempo vertical. */
export function TrackSection({ track }: TrackSectionProps) {
  const pct = track.possible_levels > 0 ? Math.round((track.approved_levels / track.possible_levels) * 100) : 0;

  return (
    <section className="mb-12">
      <div className="mb-4 flex items-center gap-3">
        <h2
          className={`text-aux font-semibold uppercase tracking-wide ${
            track.unlocked ? "text-ink" : "text-ink-disabled"
          }`}
        >
          {track.title}
        </h2>
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

      <ol className="flex flex-col">
        {track.scenario_states.map((scenario, index) => (
          <li key={scenario.slug} className="flex gap-4">
            <div className="flex flex-col items-center pt-5">
              <TimelineMark mark={scenarioMark(scenario)} />
              {index < track.scenario_states.length - 1 && <div className="my-1 w-px flex-1 bg-line" />}
            </div>
            <div className="min-w-0 flex-1 pb-3">
              <ScenarioCard trackTitle={track.title} scenario={scenario} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
