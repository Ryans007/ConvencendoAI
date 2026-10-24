import type { AttemptReport } from "../../api/attemptReport";
import { hintsUsageText } from "./hintsUsage";

interface ScoreSummaryProps {
  report: AttemptReport;
}

/** Cartão do topo do relatório: a nota final, a aprovação, o resumo do avaliador e as dicas. */
export default function ScoreSummary({ report }: ScoreSummaryProps) {
  const hints = hintsUsageText(report.hints_enabled, report.hints_used);

  return (
    <section className="mb-6 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card-focus">
      <div className="flex items-center gap-5">
        <div className="flex items-baseline gap-1">
          <span
            className={`text-[56px] font-semibold leading-none tracking-tight ${
              report.passed ? "text-brand-strong" : "text-ink"
            }`}
          >
            {report.final_score}
          </span>
          <span className="text-scenario font-medium text-ink-disabled">/100</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <span
            className={`inline-flex w-fit items-center gap-1.5 rounded-pill px-3 py-1 text-score font-semibold ${
              report.passed ? "bg-brand-soft text-brand-strong" : "bg-line-strong text-ink"
            }`}
          >
            {report.passed ? "Aprovado" : "Não atingiu a nota"}
          </span>
          <span className="text-aux text-ink-muted">
            {report.passed ? "Cenário concluído." : "Você pode tentar de novo."}
          </span>
        </div>
      </div>

      <div className="h-px bg-line" />

      <div className="flex flex-col gap-2.5">
        <h2 className="text-aux font-semibold uppercase tracking-wide text-ink-muted">
          Resumo do avaliador
        </h2>
        <p className="text-scenario leading-relaxed text-ink">{report.feedback}</p>
      </div>

      {hints && <span className="text-aux text-ink-muted">{hints}</span>}
    </section>
  );
}
