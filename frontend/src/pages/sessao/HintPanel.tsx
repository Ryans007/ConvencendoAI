import type { SessionHint } from "../../services/liveSession";

interface HintPanelProps {
  hint: SessionHint;
  canRequest: boolean;
  onRequest: () => void;
}

/**
 * A dica da vez do aluno: o botao para pedi-la e, depois do pedido, a sugestao de resposta
 * em portugues, que o aluno precisa dizer em ingles. O botao so aparece antes de a dica
 * ser pedida e enquanto o aluno nao esta gravando; a sugestao continua visivel durante a
 * gravacao, para ele poder ler enquanto fala.
 */
export function HintPanel({ hint, canRequest, onRequest }: HintPanelProps) {
  if (hint.status === "idle") {
    if (!canRequest) {
      return null;
    }
    return (
      <button
        type="button"
        onClick={onRequest}
        aria-label="Ver uma sugestão de resposta em português"
        className="rounded-pill border border-brand-line bg-brand-soft px-5 py-2 text-scenario font-medium text-brand-strong hover:border-brand-line-strong"
      >
        Dica
      </button>
    );
  }

  if (hint.status === "loading") {
    return (
      <span role="status" className="text-scenario text-ink-muted">
        Preparando sua dica...
      </span>
    );
  }

  if (hint.status === "unavailable") {
    return (
      <span role="status" className="max-w-[520px] text-center text-scenario text-warn-strong">
        A dica não está disponível agora. Você pode responder mesmo assim.
      </span>
    );
  }

  return (
    <div
      role="status"
      className="flex max-w-[520px] flex-col gap-1.5 rounded-card border border-brand-line bg-brand-soft px-5 py-4"
    >
      <span className="text-aux font-semibold uppercase tracking-wide text-brand-strong">
        Sugestão — diga em inglês
      </span>
      <span className="text-scenario leading-relaxed text-ink">{hint.text}</span>
    </div>
  );
}
