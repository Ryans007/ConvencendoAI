import type { ReactNode } from "react";

import type { RoundItem } from "../../api/reviewRound";
import { filledBoxes, intervalLabel, originLabel } from "./itemLabels";

interface ReviewItemCardProps {
  item: RoundItem;
  now: Date;
  step: 1 | 2;
  reference: string;
  discardable: boolean;
  confirmingDiscard: boolean;
  onAskDiscard: () => void;
  onCancelDiscard: () => void;
  onConfirmDiscard: () => void;
  children: ReactNode;
}

const STEP_TITLES = {
  1: "Fale a frase correta",
  2: "Agora fale uma frase nova usando a mesma estrutura",
} as const;

/**
 * Cartão do item da rodada: o que o aluno disse e de onde veio, a nota que dá o contexto
 * desde a primeira tentativa (quando o item tem uma), o pedido da etapa e, embaixo, a área
 * que muda com a fase (gravar, analisar, resultado). O "Não disse isso" fica no cartão,
 * porque descarta o item inteiro e não só a resposta da vez.
 */
export function ReviewItemCard({
  item,
  now,
  step,
  reference,
  discardable,
  confirmingDiscard,
  onAskDiscard,
  onCancelDiscard,
  onConfirmDiscard,
  children,
}: ReviewItemCardProps) {
  const filled = filledBoxes(item);

  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card-focus">
      <div className="flex flex-col gap-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <span className="text-aux text-ink-muted">{originLabel(item, now)}</span>
          <div className="flex items-center gap-2">
            <div aria-hidden="true" className="flex gap-[3px]">
              {[1, 2, 3, 4, 5].map((position) => (
                <span
                  key={position}
                  className={`h-1 w-3 rounded-pill ${position <= filled ? "bg-brand" : "bg-line"}`}
                />
              ))}
            </div>
            <span className="text-[12px] text-ink-muted">{intervalLabel(item)}</span>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-aux text-ink-muted">Você disse:</span>
          <span lang="en" className="text-[20px] font-medium leading-snug tracking-tight">
            {item.said}
          </span>
        </div>

        {item.note && (
          <p className="text-score leading-relaxed text-ink-muted">
            <span className="font-semibold text-ink/80">Contexto:</span> {item.note}
          </p>
        )}

        {discardable && !confirmingDiscard && (
          <button
            type="button"
            onClick={onAskDiscard}
            className="self-start text-aux text-ink-muted underline underline-offset-[3px] hover:text-ink"
          >
            Não disse isso
          </button>
        )}

        {confirmingDiscard && (
          <div
            role="group"
            aria-label="Confirmar descarte"
            className="flex flex-wrap items-center gap-2.5 rounded-[12px] bg-app px-3.5 py-3"
          >
            <span className="min-w-[140px] flex-1 text-score font-medium">Descartar este item?</span>
            <button
              type="button"
              onClick={onCancelDiscard}
              className="rounded-pill border border-line bg-surface px-4 py-2 text-aux font-medium text-ink/80"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={onConfirmDiscard}
              className="rounded-pill bg-ink px-4 py-2 text-aux font-semibold text-white"
            >
              Descartar
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-5 border-t border-line p-6">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2.5">
            <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Etapa {step} de 2
            </span>
            <div aria-hidden="true" className="flex gap-[3px]">
              <span className="h-1 w-4 rounded-pill bg-brand" />
              <span className={`h-1 w-4 rounded-pill ${step === 2 ? "bg-brand" : "bg-line"}`} />
            </div>
          </div>
          <h2 className="text-[17px] font-semibold leading-snug tracking-tight">{STEP_TITLES[step]}</h2>
          {step === 2 && reference && (
            <p className="text-aux leading-relaxed text-ink-muted">
              Vale qualquer assunto, desde que a estrutura esteja certa. Referência:{" "}
              <span lang="en" className="font-medium text-ink/80">
                {reference}
              </span>
            </p>
          )}
        </div>

        {children}
      </div>
    </div>
  );
}
