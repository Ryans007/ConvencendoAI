import { Link } from "react-router-dom";

import { useReviewSummary } from "../../hooks/useReviewSummary";
import { REVIEW_INTERVAL_LABELS, reviewStart } from "./reviewStart";

/**
 * Tela inicial da Revisão: quantos itens esperam o aluno e quando volta o próximo.
 *
 * A rodada em si ainda não existe, então "Começar rodada" aparece desabilitado.
 */
export default function RevisaoPage() {
  const { data: summary, isLoading, isError } = useReviewSummary();
  const start = summary ? reviewStart(summary, new Date()) : null;

  return (
    <main className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-[-120px] h-[420px] w-[820px] -translate-x-1/2 bg-[radial-gradient(ellipse_at_center,rgb(0_214_143/0.18),rgb(0_214_143/0)_68%)]"
      />

      <div className="relative mx-auto flex max-w-[640px] flex-col gap-6 px-5 py-8 lg:px-10 lg:py-12">
        <h1 className="text-page-title font-semibold tracking-tight">Revisão</h1>

        {isLoading && <p className="text-scenario text-ink-muted">Carregando sua revisão...</p>}

        {isError && (
          <p className="text-scenario text-warn-strong">
            Não foi possível carregar sua revisão agora. Tente novamente em instantes.
          </p>
        )}

        {start?.kind === "due" && (
          <>
            <section className="flex flex-col items-start gap-5 rounded-card border border-line bg-surface p-7 shadow-card-focus">
              <div className="flex flex-col gap-2">
                <h2 className="text-[20px] font-semibold tracking-tight">{start.title}</h2>
                <p className="text-score text-ink-muted">Cada rodada tem até 5 itens, uns 3 a 4 minutos.</p>
              </div>
              <button
                type="button"
                disabled
                className="flex cursor-not-allowed items-center gap-2.5 rounded-pill bg-line-strong px-6 py-3 text-[15px] font-semibold text-ink-muted"
              >
                Começar rodada
                <span className="rounded-pill bg-surface px-2 py-0.5 text-[11px] font-medium text-ink-muted">
                  em breve
                </span>
              </button>
            </section>

            <section className="flex flex-col gap-3 px-1">
              <p className="text-aux text-ink-muted">
                Cada item volta em intervalos que crescem quando você acerta as duas etapas de primeira:
              </p>
              <ul className="flex flex-wrap items-center gap-1.5">
                {REVIEW_INTERVAL_LABELS.map((label) => (
                  <li
                    key={label}
                    className="rounded-pill border border-line bg-surface px-2.5 py-1 text-[12px] font-medium text-ink/80"
                  >
                    {label}
                  </li>
                ))}
                <li className="rounded-pill bg-brand-soft px-2.5 py-1 text-[12px] font-medium text-brand-strong">
                  ✓ Dominado
                </li>
              </ul>
            </section>
          </>
        )}

        {start?.kind === "none" && (
          <section className="flex items-start gap-4 rounded-card border border-line bg-surface p-7 shadow-card">
            <div
              aria-hidden="true"
              className="flex h-9 w-9 flex-none items-center justify-center rounded-pill bg-brand-soft text-[15px] font-bold text-brand-strong"
            >
              ✓
            </div>
            <div className="flex flex-col gap-1.5 pt-0.5">
              <h2 className="text-[17px] font-semibold tracking-tight">Nada para revisar hoje.</h2>
              <p className="text-score text-ink-muted">{start.nextReview}</p>
            </div>
          </section>
        )}

        {start?.kind === "empty" && (
          <section className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-7 shadow-card">
            <div className="flex flex-col gap-2">
              <h2 className="text-[17px] font-semibold tracking-tight">Ainda não há itens para revisar</h2>
              <p className="text-score leading-relaxed text-ink-muted">
                Os erros de inglês que você comete nas cenas aparecem aqui, para você retomar com o
                professor.
              </p>
            </div>
            <Link to="/jornada" className="text-score font-semibold text-brand-strong hover:underline">
              Ir para a jornada &rarr;
            </Link>
          </section>
        )}
      </div>
    </main>
  );
}
