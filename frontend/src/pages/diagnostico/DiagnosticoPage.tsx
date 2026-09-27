import type { ComponentState } from "../../api/health";
import { useHealth } from "../../hooks/useHealth";

const ROTULO: Record<ComponentState, string> = {
  ok: "no ar",
  unreachable: "inalcancavel",
};

interface LinhaProps {
  nome: string;
  estado: ComponentState;
}

function Linha({ nome, estado }: LinhaProps) {
  const saudavel = estado === "ok";
  const pilula = saudavel
    ? "bg-brand-soft text-brand-strong"
    : "bg-warn-soft text-warn-strong";

  return (
    <div className="flex items-center justify-between border-b border-line py-3 last:border-b-0">
      <span className="text-scenario font-medium">{nome}</span>
      <span className={`rounded-pill px-3 py-1 text-score font-semibold ${pilula}`}>
        {ROTULO[estado]}
      </span>
    </div>
  );
}

/** Pagina de sanidade: confirma que o frontend alcanca a API, e a API o banco. */
export default function DiagnosticoPage() {
  const { status, error, loading } = useHealth();

  return (
    <main className="mx-auto max-w-[480px] px-8 py-20">
      <h1 className="text-page-title font-semibold tracking-tight">ConvencendoAI</h1>
      <p className="mt-1 text-aux text-ink-muted">Verificacao de infraestrutura</p>

      <section className="mt-8 rounded-card border border-line bg-surface p-6 shadow-card">
        {loading && <p className="text-aux text-ink-muted">Consultando o backend...</p>}

        {error !== null && (
          <div>
            <p className="text-scenario font-medium text-warn-strong">Backend inalcancavel</p>
            <p className="mt-2 text-aux text-ink-muted">{error}</p>
          </div>
        )}

        {status !== null && (
          <div>
            <Linha nome="Aplicacao" estado={status.application} />
            <Linha nome="Banco de dados" estado={status.database} />
          </div>
        )}
      </section>
    </main>
  );
}
