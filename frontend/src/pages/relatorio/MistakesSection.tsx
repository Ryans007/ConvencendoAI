import type { AttemptMistake } from "../../api/attemptReport";
import { useMistakeAudio } from "../../hooks/useMistakeAudio";
import MistakeCard from "./MistakeCard";

interface MistakesSectionProps {
  attemptId: number;
  mistakes: AttemptMistake[];
}

/** Seção "O que você pode melhorar": um cartão por erro da sessão; sem erros, não aparece. */
export default function MistakesSection({ attemptId, mistakes }: MistakesSectionProps) {
  const { playingId, error, listen } = useMistakeAudio(attemptId);

  if (mistakes.length === 0) {
    return null;
  }

  return (
    <section className="mb-6 flex flex-col gap-5 rounded-card border border-line bg-surface p-7 shadow-card">
      <h2 className="text-aux font-semibold uppercase tracking-wide text-ink-muted">
        O que você pode melhorar
      </h2>
      <div className="flex flex-col gap-4">
        {mistakes.map((mistake) => (
          <MistakeCard
            key={mistake.id}
            mistake={mistake}
            playing={playingId === mistake.id}
            listenDisabled={playingId !== null}
            onListen={() => void listen(mistake.id)}
          />
        ))}
      </div>
      {error && (
        <p role="alert" className="text-aux text-warn-strong">
          {error}
        </p>
      )}
    </section>
  );
}
