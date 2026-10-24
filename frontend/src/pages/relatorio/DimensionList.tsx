import type { ScoreBreakdown, SpeechMetrics } from "../../api/attemptReport";
import { DIMENSION_LABELS } from "./dimensionLabels";
import { dimensionMeasures } from "./reportText";

const WEAK_RATIO = 0.7;

interface DimensionListProps {
  breakdowns: ScoreBreakdown[];
  metrics: SpeechMetrics | null;
}

/**
 * As dimensões avaliadas, cada uma com a barra da nota, o comentário do avaliador e, em
 * fluência e vocabulário, as medidas da fala. Uma barra abaixo de 70% do peso fica em alerta.
 */
export default function DimensionList({ breakdowns, metrics }: DimensionListProps) {
  return (
    <section className="mb-6 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card">
      <h2 className="text-aux font-semibold uppercase tracking-wide text-ink-muted">Dimensões</h2>
      <div className="flex flex-col gap-[22px]">
        {breakdowns.map((breakdown) => {
          const ratio = breakdown.weight > 0 ? breakdown.value / breakdown.weight : 0;
          const weak = ratio < WEAK_RATIO;
          const measures = dimensionMeasures(breakdown.dimension, metrics);
          return (
            <div key={breakdown.dimension} className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-scenario font-medium">
                  {DIMENSION_LABELS[breakdown.dimension] ?? breakdown.dimension}
                </span>
                <span className={`text-score font-semibold ${weak ? "text-warn-strong" : "text-brand-strong"}`}>
                  {breakdown.value} / {breakdown.weight}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-pill bg-line-strong">
                <div
                  className={`h-full rounded-pill ${weak ? "bg-warn" : "bg-brand"}`}
                  style={{ width: `${Math.round(ratio * 100)}%` }}
                />
              </div>
              {breakdown.comment && (
                <p className="text-[15px] leading-relaxed text-ink/80">{breakdown.comment}</p>
              )}
              {measures.length > 0 && (
                <ul className="flex flex-wrap gap-2">
                  {measures.map((measure) => (
                    <li key={measure} className="rounded-pill bg-app px-3 py-1 text-aux text-ink-muted">
                      {measure}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
