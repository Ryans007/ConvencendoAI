import type { AttemptMistake } from "../../api/attemptReport";
import ListenButton from "./ListenButton";

interface MistakeCardProps {
  mistake: AttemptMistake;
  playing: boolean;
  listenDisabled: boolean;
  onListen: () => void;
}

/**
 * Um erro da sessão: o que o aluno disse, a forma correta à vista com "Ouvir", a explicação
 * da regra e os exemplos. A explicação e os exemplos só aparecem quando existem, porque os
 * erros gravados antes deles não os têm.
 */
export default function MistakeCard({ mistake, playing, listenDisabled, onListen }: MistakeCardProps) {
  return (
    <article className="flex flex-col gap-4 rounded-[14px] border border-line p-5">
      <div className="flex flex-col gap-1">
        <span className="text-aux text-ink-muted">Você disse:</span>
        <span lang="en" className="text-scenario leading-snug text-ink/80">
          {mistake.produced}
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] bg-app px-4 py-3.5">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-[12px] font-medium text-ink-muted">Forma correta</span>
          <span lang="en" className="text-scenario font-semibold leading-snug">
            {mistake.correct}
          </span>
        </div>
        <ListenButton playing={playing} disabled={listenDisabled} onListen={onListen} />
      </div>

      {mistake.explanation && (
        <div className="flex flex-col gap-1">
          <span className="text-aux font-semibold text-ink">Por quê</span>
          <p className="text-[15px] leading-relaxed text-ink/80">{mistake.explanation}</p>
        </div>
      )}

      {mistake.examples.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-aux font-semibold text-ink">Exemplos</span>
          <ul className="flex flex-col gap-1">
            {mistake.examples.map((example) => (
              <li key={example} lang="en" className="text-[15px] leading-relaxed text-ink/80">
                {example}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
