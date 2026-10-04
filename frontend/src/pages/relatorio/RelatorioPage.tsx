import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useAttemptReport } from "../../hooks/useAttemptReport";
import { DIMENSION_LABELS } from "./dimensionLabels";
import { hintsUsageText } from "./hintsUsage";
import { prettifySlug, type ReportContext } from "./reportContext";

/** Tela de relatório: nota final, sub-notas por dimensão e critérios de uma tentativa. */
export default function RelatorioPage() {
  const { attemptId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const reportContext = (location.state as { reportContext?: ReportContext } | null)?.reportContext;
  const { data: report, isLoading, error } = useAttemptReport(Number(attemptId));

  const unavailable = error instanceof ApiError && error.status === 404;

  const orderedCriteria = report
    ? [...report.criteria].sort((a, b) => Number(a.met) - Number(b.met))
    : [];

  return (
    <div className="min-h-screen bg-app px-8 py-12">
      <div className="mx-auto max-w-[760px]">
        {isLoading && <p className="text-scenario text-ink-muted">Carregando o relatório...</p>}

        {unavailable && (
          <div className="flex flex-col items-center gap-6 py-20 text-center">
            <p className="text-scenario text-ink-muted">
              Este relatório não está disponível.
            </p>
            <button
              type="button"
              onClick={() => navigate("/jornada")}
              className="rounded-pill bg-brand px-6 py-3 text-scenario font-semibold text-white"
            >
              Voltar para a jornada
            </button>
          </div>
        )}

        {report && (
          <>
            <div className="mb-7 flex flex-col gap-2">
              {reportContext?.trackTitle && (
                <span className="text-aux font-semibold uppercase tracking-wide text-brand-strong">
                  {reportContext.trackTitle}
                </span>
              )}
              <h1 className="text-[26px] font-semibold tracking-tight">
                {reportContext?.scenarioTitle ?? prettifySlug(report.scenario)}
              </h1>
              <span className="text-scenario text-ink-muted">
                {reportContext?.levelLabel ?? `Nível ${report.level}`}
              </span>
            </div>

            <div className="mb-6 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card-focus">
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
                <span className="text-aux font-semibold uppercase tracking-wide text-ink-muted">
                  Feedback do avaliador
                </span>
                <p className="text-scenario leading-relaxed text-ink">{report.feedback}</p>
              </div>

              {hintsUsageText(report.hints_enabled, report.hints_used) && (
                <span className="text-aux text-ink-muted">
                  {hintsUsageText(report.hints_enabled, report.hints_used)}
                </span>
              )}
            </div>

            <div className="mb-6 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card">
              <span className="text-aux font-semibold uppercase tracking-wide text-ink-muted">Dimensões</span>
              <div className="flex flex-col gap-[18px]">
                {report.score_breakdowns.map((breakdown) => {
                  const ratio = breakdown.weight > 0 ? breakdown.value / breakdown.weight : 0;
                  const weak = ratio < 0.7;
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
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="mb-8 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card">
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-aux font-semibold uppercase tracking-wide text-ink-muted">
                  Critérios de aceite
                </span>
                <span className="text-aux font-medium text-ink-muted">
                  {report.criteria.filter((c) => c.met).length} de {report.criteria.length} cumpridos
                </span>
              </div>
              <div className="flex flex-col gap-3.5">
                {orderedCriteria.map((criterion) => (
                  <div key={criterion.code} className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-pill text-[11px] font-bold ${
                        criterion.met ? "bg-brand text-white" : "border border-warn bg-white text-warn-strong"
                      }`}
                    >
                      {criterion.met ? "✓" : "✕"}
                    </div>
                    <span className={`text-scenario leading-snug ${criterion.met ? "text-ink" : "text-ink"}`}>
                      {criterion.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => navigate("/jornada")}
              className="w-full rounded-pill bg-brand px-6 py-4 text-scenario font-semibold text-white shadow-card-focus"
            >
              Voltar para a jornada
            </button>
          </>
        )}
      </div>
    </div>
  );
}
