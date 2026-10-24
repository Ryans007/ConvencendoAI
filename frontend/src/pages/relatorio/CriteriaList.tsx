import type { AttemptCriterion } from "../../api/attemptReport";

interface CriteriaListProps {
  criteria: AttemptCriterion[];
}

/** Os critérios de aceite da tentativa, os não cumpridos primeiro. */
export default function CriteriaList({ criteria }: CriteriaListProps) {
  const ordered = [...criteria].sort((a, b) => Number(a.met) - Number(b.met));

  return (
    <section className="mb-6 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-aux font-semibold uppercase tracking-wide text-ink-muted">
          Critérios de aceite
        </h2>
        <span className="text-aux font-medium text-ink-muted">
          {criteria.filter((criterion) => criterion.met).length} de {criteria.length} cumpridos
        </span>
      </div>
      <ul className="flex flex-col gap-3.5">
        {ordered.map((criterion) => (
          <li key={criterion.code} className="flex items-start gap-3">
            <div
              aria-hidden="true"
              className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-pill text-[11px] font-bold ${
                criterion.met ? "bg-brand text-white" : "border border-warn bg-white text-warn-strong"
              }`}
            >
              {criterion.met ? "✓" : "✕"}
            </div>
            <span className="text-scenario leading-snug text-ink">
              <span className="sr-only">{criterion.met ? "Cumprido: " : "Não cumprido: "}</span>
              {criterion.text}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
