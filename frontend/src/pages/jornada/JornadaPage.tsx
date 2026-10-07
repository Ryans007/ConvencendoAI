import { useJourney } from "../../hooks/useJourney";
import { TrackSection } from "./TrackSection";

/** Tela de jornada: todas as trilhas, cenários e níveis do aluno autenticado. */
export default function JornadaPage() {
  const { data: tracks, isLoading, isError } = useJourney();

  return (
    <main className="mx-auto max-w-[760px] px-5 py-8 lg:px-8 lg:py-10">
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
    </main>
  );
}
