import { useJourney } from "../../hooks/useJourney";
import { useReviewSummary } from "../../hooks/useReviewSummary";
import { ReviewShortcutBar } from "./ReviewShortcutBar";
import { TrackSection } from "./TrackSection";

/** Tela de jornada: todas as trilhas, cenários e níveis do aluno autenticado. */
export default function JornadaPage() {
  const { data: tracks, isLoading, isError } = useJourney();
  const { data: review } = useReviewSummary();
  const due = review?.due ?? 0;

  return (
    <main className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-[-120px] h-[420px] w-[820px] -translate-x-1/2 bg-[radial-gradient(ellipse_at_center,rgb(0_214_143/0.18),rgb(0_214_143/0)_68%)]"
      />

      <div className={`relative mx-auto max-w-[760px] px-5 pt-8 lg:px-8 lg:pt-10 ${due > 0 ? "pb-28" : "pb-10"}`}>
        <h1 className="mb-8 text-page-title font-semibold tracking-tight">Sua jornada</h1>

        {isLoading && <p className="text-scenario text-ink-muted">Carregando sua jornada...</p>}

        {isError && (
          <p className="text-scenario text-warn-strong">
            Não foi possível carregar sua jornada agora. Tente novamente em instantes.
          </p>
        )}

        {tracks?.map((track) => (
          <TrackSection key={track.slug} track={track} />
        ))}
      </div>

      {due > 0 && <ReviewShortcutBar due={due} />}
    </main>
  );
}
