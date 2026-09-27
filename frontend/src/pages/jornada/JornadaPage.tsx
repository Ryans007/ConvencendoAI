import { Logo } from "../../components/Logo";
import { LogoutLink } from "../../components/LogoutLink";
import { useJourney } from "../../hooks/useJourney";
import { TrackSection } from "./TrackSection";

/** Tela de jornada: todas as trilhas, cenarios e niveis do aluno autenticado. */
export default function JornadaPage() {
  const { data: tracks, isLoading, isError } = useJourney();

  const activeTrack = tracks?.find((track) => track.unlocked && !track.completed) ?? tracks?.[0];

  return (
    <div className="min-h-screen bg-app">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-6 border-b border-line bg-surface/90 px-8 py-4 backdrop-blur">
        <div className="flex flex-1 items-center gap-2.5">
          <Logo size={24} />
          <span className="text-scenario font-semibold">ConvencendoAI</span>
        </div>
        <div className="text-page-title font-semibold tracking-tight">Sua jornada</div>
        <div className="flex flex-1 items-center justify-end gap-4">
          {activeTrack && <span className="text-aux text-ink-muted">{activeTrack.student_role}</span>}
          <LogoutLink />
        </div>
      </header>

      <main className="mx-auto max-w-[760px] px-8 py-10">
        {isLoading && <p className="text-scenario text-ink-muted">Carregando sua jornada...</p>}

        {isError && (
          <p className="text-scenario text-warn-strong">
            Nao foi possivel carregar sua jornada agora. Tente novamente em instantes.
          </p>
        )}

        {tracks?.map((track) => (
          <TrackSection key={track.slug} track={track} />
        ))}
      </main>
    </div>
  );
}
