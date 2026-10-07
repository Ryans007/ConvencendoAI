import { Link } from "react-router-dom";

interface ReviewShortcutBarProps {
  due: number;
}

/**
 * Barra fixa no pé da jornada com o atalho para a Revisão. Em telas largas ela começa depois
 * do menu lateral, que ocupa a esquerda, para não ficar por cima dele.
 */
export function ReviewShortcutBar({ due }: ReviewShortcutBarProps) {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-10 px-5 pb-4 lg:left-[248px]">
      <div className="pointer-events-auto mx-auto flex max-w-[760px] items-center justify-between gap-4 rounded-card border border-line bg-surface px-5 py-3 shadow-card-focus">
        <div className="flex flex-col">
          <span className="text-scenario font-semibold tracking-tight">Praticar revisão</span>
          <span className="text-aux text-ink-muted">
            {due} {due === 1 ? "item pendente" : "itens pendentes"}
          </span>
        </div>
        <Link
          to="/revisao"
          className="rounded-pill bg-brand px-5 py-2 text-score font-semibold text-white shadow-card-focus hover:bg-brand-strong"
        >
          Abrir revisão
        </Link>
      </div>
    </div>
  );
}
