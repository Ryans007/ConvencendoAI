import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useAttemptReport } from "../../hooks/useAttemptReport";
import CriteriaList from "./CriteriaList";
import DimensionList from "./DimensionList";
import MistakesSection from "./MistakesSection";
import { prettifySlug, type ReportContext } from "./reportContext";
import ScoreSummary from "./ScoreSummary";
import ScoringExplanationSection from "./ScoringExplanationSection";

/**
 * Tela de relatório de uma tentativa: nota e resumo, os erros da sessão, as dimensões com
 * comentário e medidas, os critérios e a explicação de como a nota foi calculada.
 */
export default function RelatorioPage() {
  const { attemptId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const reportContext = (location.state as { reportContext?: ReportContext } | null)?.reportContext;
  const { data: report, isLoading, error } = useAttemptReport(Number(attemptId));

  const unavailable = error instanceof ApiError && error.status === 404;

  return (
    <div className="px-5 py-8 lg:px-8 lg:py-12">
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

            <ScoreSummary report={report} />
            <MistakesSection attemptId={report.id} mistakes={report.mistakes} />
            <DimensionList breakdowns={report.score_breakdowns} metrics={report.speech_metrics} />
            <CriteriaList criteria={report.criteria} />
            <ScoringExplanationSection report={report} />

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
