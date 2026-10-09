import type { AnswerResponse, Attempt } from "../../api/reviewRound";
import { verdictLabel } from "../../services/reviewRound";

interface AnswerResultProps {
  response: AnswerResponse;
  attempt: Attempt;
  actionLabel: string;
  listening: boolean;
  onListen: () => void;
  onAction: () => void;
}

/**
 * O que o aluno vê depois de uma resposta: o veredito, o que o sistema ouviu, o feedback do
 * professor e, ao fim da etapa, a forma correta com o botão de ouvir. Depois de um primeiro
 * erro avisa que, se a fala foi ouvida errado, basta tentar de novo: a transcrição pode errar,
 * e o aluno não deve ser punido por isso.
 */
export function AnswerResult({
  response,
  attempt,
  actionLabel,
  listening,
  onListen,
  onAction,
}: AnswerResultProps) {
  const right = response.correct === true;
  const firstMiss = !right && attempt === 1;

  return (
    <div className="flex flex-col gap-4">
      <span
        className={`inline-flex w-fit items-center gap-2 rounded-pill px-3.5 py-1.5 text-score font-semibold ${
          right ? "bg-brand-soft text-brand-strong" : "bg-warn-soft text-warn-strong"
        }`}
      >
        <span aria-hidden="true" className="text-[12px] font-bold leading-none">
          {right ? "✓" : "✕"}
        </span>
        {verdictLabel(response, attempt)}
      </span>

      <div className="flex flex-col gap-1">
        <span className="text-aux text-ink-muted">Ouvimos:</span>
        <span lang="en" className="text-scenario font-medium leading-snug">
          {response.heard}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-aux text-ink-muted">Professor</span>
        <p className="text-[15px] leading-relaxed text-ink/80">{response.feedback}</p>
      </div>

      {response.revealed_correct && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] bg-app px-4 py-3.5">
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-[12px] font-medium text-ink-muted">Forma correta</span>
            <span lang="en" className="text-scenario font-semibold leading-snug">
              {response.revealed_correct}
            </span>
          </div>
          <button
            type="button"
            onClick={onListen}
            disabled={listening}
            aria-label="Ouvir a frase correta em inglês"
            className="inline-flex items-center gap-2 rounded-pill border border-brand-line bg-surface px-3.5 py-2 text-aux font-semibold text-brand-strong hover:border-brand disabled:cursor-default"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M2.5 6h2.5l3.5-3v10L5 10H2.5z" />
              <path d="M11 5.5a3.5 3.5 0 0 1 0 5" />
              <path d="M12.8 3.6a6 6 0 0 1 0 8.8" />
            </svg>
            <span>{listening ? "Tocando…" : "Ouvir"}</span>
          </button>
        </div>
      )}

      {firstMiss && (
        <span className="text-aux text-ink-muted">Se ouvimos errado, é só tentar de novo.</span>
      )}

      <button
        type="button"
        onClick={onAction}
        className="mt-1 w-fit rounded-pill bg-brand px-6 py-3 text-[15px] font-semibold text-white shadow-[0_6px_20px_rgb(0_214_143/0.28)] hover:bg-brand-strong"
      >
        {actionLabel}
      </button>
    </div>
  );
}
