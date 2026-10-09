import { useState } from "react";

import type { RoundItem } from "../../api/reviewRound";
import { useReviewRound } from "../../hooks/useReviewRound";
import { resultActionLabel, type RoundPhase } from "../../services/reviewRound";
import { AnswerResult } from "./AnswerResult";
import { ReviewItemCard } from "./ReviewItemCard";
import { RoundSummary } from "./RoundSummary";
import { TalkButton } from "./TalkButton";

interface RoundScreenProps {
  items: RoundItem[];
  totalDue: number;
  onReload: () => void;
}

const TALK_PHASES: RoundPhase[] = ["idle", "recording", "not_heard", "mic_denied"];
const DISCARDABLE_PHASES: RoundPhase[] = [
  "idle",
  "not_heard",
  "mic_denied",
  "unavailable",
  "result",
  "confirm_discard",
];

const ANNOUNCEMENTS: Partial<Record<RoundPhase, string>> = {
  recording: "Gravando. Solte para enviar.",
  analyzing: "Analisando sua resposta...",
  not_heard: "Não consegui ouvir você. Segure o botão e fale de novo.",
  unavailable: "O serviço de IA está indisponível no momento. Tente de novo em alguns minutos.",
  summary: "Rodada concluída",
};

function Notice({ tone, children }: { tone: "info" | "warn"; children: React.ReactNode }) {
  const style =
    tone === "warn"
      ? "border border-warn/30 bg-warn-soft text-warn-strong"
      : "bg-app text-ink/80";
  return (
    <div className={`flex items-start gap-2.5 rounded-[12px] px-3.5 py-3 ${style}`}>
      <span
        aria-hidden="true"
        className="mt-px flex h-[18px] w-[18px] flex-none items-center justify-center rounded-pill border-[1.5px] border-current text-[11px] font-bold leading-none"
      >
        !
      </span>
      <div className="flex flex-col gap-1.5 text-score leading-snug">{children}</div>
    </div>
  );
}

/**
 * A rodada em andamento: o progresso, o cartão do item com a área da fase atual e, no fim, o
 * resumo. Nasce com os itens já carregados e é recriada pela página, com uma `key` nova, a cada
 * rodada, então o estado de uma rodada nunca vaza para a seguinte.
 */
export function RoundScreen({ items, totalDue, onReload }: RoundScreenProps) {
  const [now] = useState(() => new Date());
  const round = useReviewRound(items, onReload);
  const { state } = round;
  const item = state.items[state.index];

  if (state.phase === "summary") {
    return (
      <div className="flex flex-col gap-6">
        <span role="status" aria-live="polite" className="sr-only">
          {ANNOUNCEMENTS.summary}
        </span>
        <RoundSummary
          finished={state.finished}
          remaining={Math.max(0, totalDue - items.length)}
          onAnotherRound={onReload}
        />
      </div>
    );
  }

  const bodyPhase = state.phase === "confirm_discard" ? state.phaseBeforeDiscard : state.phase;
  const secondTry = state.attempt === 2 && (bodyPhase === "idle" || bodyPhase === "not_heard");
  const announcement =
    state.phase === "result" && state.last
      ? state.last.feedback
      : (ANNOUNCEMENTS[state.phase] ?? "");

  return (
    <div className="flex flex-col gap-5">
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>

      <div className="flex flex-col gap-2.5">
        <span className="text-aux font-medium text-ink-muted">
          Item {state.index + 1} de {state.items.length}
        </span>
        <div className="flex gap-1" aria-hidden="true">
          {state.items.map((entry, index) => (
            <span
              key={entry.id}
              className={`h-1 flex-1 rounded-pill ${
                index < state.index ? "bg-brand" : index === state.index ? "bg-brand-line-strong" : "bg-line"
              }`}
            />
          ))}
        </div>
      </div>

      <ReviewItemCard
        item={item}
        now={now}
        step={state.step}
        reference={state.reference}
        discardable={DISCARDABLE_PHASES.includes(state.phase)}
        confirmingDiscard={state.phase === "confirm_discard"}
        onAskDiscard={round.askDiscard}
        onCancelDiscard={round.cancelDiscard}
        onConfirmDiscard={() => void round.confirmDiscard()}
      >
        {TALK_PHASES.includes(bodyPhase) && (
          <div className="flex flex-col items-center gap-4">
            {bodyPhase === "not_heard" && (
              <div className="self-stretch">
                <Notice tone="info">Não consegui ouvir você. Segure o botão e fale de novo.</Notice>
              </div>
            )}
            {bodyPhase === "mic_denied" && (
              <div className="self-stretch">
                <Notice tone="warn">
                  Não foi possível usar o microfone. Libere o acesso a ele no navegador e tente de
                  novo.
                </Notice>
              </div>
            )}
            {secondTry && <span className="text-aux font-medium text-ink-muted">Segunda tentativa</span>}
            <TalkButton
              recording={bodyPhase === "recording"}
              onStart={() => void round.startRecording()}
              onStop={() => void round.stopRecording()}
            />
          </div>
        )}

        {bodyPhase === "analyzing" && (
          <div className="flex flex-col items-center gap-4 py-8">
            <div aria-hidden="true" className="flex items-center gap-2">
              {[0, 1, 2].map((dot) => (
                <span
                  key={dot}
                  style={{ animationDelay: `${dot * 0.2}s` }}
                  className="h-2.5 w-2.5 animate-pulse rounded-pill bg-brand"
                />
              ))}
            </div>
            <span className="text-score font-medium text-ink-muted">Analisando sua resposta...</span>
          </div>
        )}

        {bodyPhase === "unavailable" && (
          <div className="flex flex-col items-start gap-4">
            <div className="self-stretch">
              <Notice tone="warn">
                <span className="font-medium">
                  O serviço de IA está indisponível no momento. Tente de novo em alguns minutos.
                </span>
                <span className="text-aux">O que você já respondeu nesta rodada continua salvo.</span>
              </Notice>
            </div>
            <button
              type="button"
              onClick={() => void round.retryAnswer()}
              className="rounded-pill border border-line bg-surface px-5 py-2.5 text-score font-semibold hover:border-brand-line-strong"
            >
              Tentar de novo
            </button>
          </div>
        )}

        {bodyPhase === "result" && state.last && (
          <AnswerResult
            response={state.last}
            attempt={state.attempt}
            actionLabel={resultActionLabel(state)}
            listening={round.listening}
            onListen={() => void round.listen()}
            onAction={round.continueRound}
          />
        )}

        {round.actionError && <Notice tone="warn">{round.actionError}</Notice>}
      </ReviewItemCard>
    </div>
  );
}
