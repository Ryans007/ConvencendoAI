import { Link } from "react-router-dom";

import { comesBackLabel, roundCounts, type FinishedItem } from "../../services/reviewRound";

interface RoundSummaryProps {
  finished: FinishedItem[];
  remaining: number;
  onAnotherRound: () => void;
}

const COUNT_ROWS = [
  { key: "advanced", label: "Avançaram", reason: "Acertaram de primeira e voltam mais tarde" },
  { key: "repeat", label: "Repetem o intervalo", reason: "Acertaram na segunda tentativa" },
  { key: "back", label: "Voltam amanhã", reason: "Erraram e recomeçam no intervalo de 1 dia" },
  { key: "mastered", label: "Dominados", reason: "Passaram pela caixa de 30 dias" },
  { key: "discarded", label: "Descartados", reason: "Marcados como “Não disse isso”" },
] as const;

/**
 * Resumo do fim da rodada: quantos itens caíram em cada saída e a lista com quando cada um
 * volta. Com mais itens vencidos oferece outra rodada, sem limite diário.
 */
export function RoundSummary({ finished, remaining, onAnotherRound }: RoundSummaryProps) {
  const counts = roundCounts(finished);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-page-title font-semibold tracking-tight">Rodada concluída</h1>

      <div className="rounded-card border border-line bg-surface px-6 py-1.5 shadow-card-focus">
        {COUNT_ROWS.map((row, index) => (
          <div
            key={row.key}
            className={`flex items-center justify-between gap-4 py-3.5 ${
              index > 0 ? "border-t border-line" : ""
            } ${counts[row.key] === 0 ? "opacity-50" : ""}`}
          >
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="text-[15px] font-medium">{row.label}</span>
              <span className="text-aux text-ink-muted">{row.reason}</span>
            </div>
            <span className="text-[18px] font-semibold">{counts[row.key]}</span>
          </div>
        ))}
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="px-1 text-aux font-semibold uppercase tracking-[0.08em] text-ink-muted">
          Itens desta rodada
        </h2>
        <ul className="rounded-card border border-line bg-surface px-6 py-1.5 shadow-card">
          {finished.map((entry, index) => (
            <li
              key={entry.item.id}
              className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3.5 ${
                index > 0 ? "border-t border-line" : ""
              }`}
            >
              <div className="flex min-w-0 flex-1 basis-60 flex-col gap-0.5">
                <span
                  lang="en"
                  className={`text-[15px] font-medium leading-snug ${
                    entry.kind === "discarded" ? "text-ink-disabled" : "text-ink"
                  }`}
                >
                  {entry.item.said}
                </span>
                <span className="text-aux text-ink-muted">{entry.item.scenario_title}</span>
              </div>
              <span
                className={`whitespace-nowrap rounded-pill px-2.5 py-1 text-[12px] font-semibold ${
                  entry.kind === "mastered"
                    ? "bg-brand-soft text-brand-strong"
                    : "bg-line-strong text-ink/80"
                }`}
              >
                {comesBackLabel(entry)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap gap-3">
        {remaining > 0 && (
          <button
            type="button"
            onClick={onAnotherRound}
            className="rounded-pill bg-brand px-6 py-3 text-[15px] font-semibold text-white shadow-[0_6px_20px_rgb(0_214_143/0.28)] hover:bg-brand-strong"
          >
            Mais uma rodada ({remaining} {remaining === 1 ? "item restante" : "itens restantes"})
          </button>
        )}
        <Link
          to="/jornada"
          className={`rounded-pill px-6 py-3 text-[15px] font-semibold ${
            remaining > 0
              ? "border border-line bg-surface text-ink hover:border-brand-line-strong"
              : "bg-brand text-white shadow-[0_6px_20px_rgb(0_214_143/0.28)] hover:bg-brand-strong"
          }`}
        >
          Voltar para a jornada
        </Link>
      </div>
    </div>
  );
}
