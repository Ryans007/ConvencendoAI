import { Link } from "react-router-dom";

import { useRoundItems } from "../../hooks/useRoundItems";
import { RoundScreen } from "./RoundScreen";

/**
 * Tela da rodada de revisão: carrega os itens vencidos e entrega a rodada a `RoundScreen`.
 *
 * A rodada é recriada, com uma `key` nova, sempre que a busca devolve itens novos: é assim que
 * "Mais uma rodada" começa limpo, e que um conflito do servidor recarrega o que estava vencido.
 */
export default function RodadaPage() {
  const query = useRoundItems();
  const page = query.data;

  return (
    <main className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-[-120px] h-[420px] w-[820px] -translate-x-1/2 bg-[radial-gradient(ellipse_at_center,rgb(0_214_143/0.18),rgb(0_214_143/0)_68%)]"
      />

      <div className="relative mx-auto max-w-[640px] px-5 py-8 lg:px-10 lg:py-12">
        {(query.isPending || query.isFetching) && (
          <p className="text-scenario text-ink-muted">Carregando sua rodada...</p>
        )}

        {query.isError && !query.isFetching && (
          <div className="flex flex-col items-start gap-4">
            <p className="text-scenario text-warn-strong">
              Não foi possível carregar sua rodada agora. Tente novamente em instantes.
            </p>
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="rounded-pill border border-line bg-surface px-5 py-2.5 text-score font-semibold"
            >
              Tentar de novo
            </button>
          </div>
        )}

        {page && !query.isFetching && page.results.length === 0 && (
          <div className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-7 shadow-card">
            <h1 className="text-[17px] font-semibold tracking-tight">Nada para revisar agora.</h1>
            <Link to="/revisao" className="text-score font-semibold text-brand-strong hover:underline">
              Voltar para a revisão
            </Link>
          </div>
        )}

        {page && !query.isFetching && page.results.length > 0 && (
          <RoundScreen
            key={query.dataUpdatedAt}
            items={page.results}
            totalDue={page.count}
            onReload={() => void query.refetch()}
          />
        )}
      </div>
    </main>
  );
}
