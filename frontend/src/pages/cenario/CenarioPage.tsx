import { useLocation, useNavigate, useParams } from "react-router-dom";

import { AvatarPlaceholder } from "../../components/AvatarPlaceholder";
import { LogoutLink } from "../../components/LogoutLink";
import { useScenarioBriefing } from "../../hooks/useScenarioBriefing";
import type { ReportContext } from "../relatorio/reportContext";

/** Tela de briefing: o que o aluno precisa saber antes de comecar um cenario e nivel. */
export default function CenarioPage() {
  const { scenarioSlug = "", levelOrder = "" } = useParams();
  const level = Number(levelOrder);
  const navigate = useNavigate();
  const location = useLocation();
  const trackTitle = (location.state as { trackTitle?: string } | null)?.trackTitle;

  const { data: briefing, isLoading, isError } = useScenarioBriefing(scenarioSlug, level);

  return (
    <div className="min-h-screen bg-app px-8 py-10">
      <div className="mx-auto flex max-w-[760px] items-center justify-between">
        <button
          type="button"
          onClick={() => navigate("/jornada")}
          className="flex items-center gap-2 text-scenario font-medium text-ink-muted hover:text-ink"
        >
          <span>&larr;</span>
          <span>Voltar para a jornada</span>
        </button>
        <LogoutLink />
      </div>

      <div className="mx-auto mt-10 max-w-[760px]">
        {isLoading && <p className="text-scenario text-ink-muted">Carregando o briefing...</p>}

        {isError && (
          <p className="text-scenario text-warn-strong">
            Nao foi possivel carregar este cenario agora. Volte para a jornada e tente de novo.
          </p>
        )}

        {briefing && (
          <>
            <div className="mb-10 flex flex-col gap-2.5">
              {trackTitle && (
                <span className="text-aux font-semibold uppercase tracking-wide text-brand-strong">
                  {trackTitle}
                </span>
              )}
              <h1 className="text-[32px] font-semibold tracking-tight">{briefing.title}</h1>
              <span className="text-scenario text-ink-muted">
                {briefing.difficulty_label}, nivel {briefing.expected_cefr}
              </span>
            </div>

            <div className="mb-6 rounded-card border border-line bg-surface p-6 shadow-card-focus">
              <div className="mb-2.5 flex items-center gap-2">
                <span className="text-aux font-semibold uppercase tracking-wide text-brand-strong">Objetivo</span>
              </div>
              <p className="text-[17px] font-medium leading-snug">{briefing.objective}</p>
            </div>

            <div className="mb-6 rounded-card border border-line bg-surface p-6 shadow-card">
              <span className="text-aux font-semibold uppercase tracking-wide text-ink-muted">Contexto</span>
              <p className="mt-2.5 text-scenario leading-relaxed text-ink">{briefing.context}</p>
            </div>

            <div className="mb-6 rounded-card border border-line bg-surface p-6 shadow-card">
              <span className="text-aux font-semibold uppercase tracking-wide text-ink-muted">Elenco</span>
              <div className="mt-4 flex flex-col gap-4">
                {briefing.roles.map((role) => (
                  <div key={role.name} className="flex items-center gap-3.5">
                    <AvatarPlaceholder size={40} />
                    <div className="flex flex-col gap-0.5">
                      <span className="text-scenario font-medium">{role.name}</span>
                      <span className="text-aux text-ink-muted">{role.scene_function}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {briefing.memory_summary && (
              <div className="mb-10 flex items-start gap-2.5 px-1">
                <span className="text-aux text-ink-disabled">&#10003;</span>
                <span className="text-aux leading-relaxed text-ink-muted">{briefing.memory_summary}</span>
              </div>
            )}

            <button
              type="button"
              onClick={() => {
                const reportContext: ReportContext = {
                  scenarioTitle: briefing.title,
                  levelLabel: `${briefing.difficulty_label}, nível ${briefing.expected_cefr}`,
                  trackTitle,
                };
                navigate(`/sessao/${scenarioSlug}/${level}`, {
                  state: { maxTurns: briefing.max_turns, reportContext },
                });
              }}
              className="w-full rounded-pill bg-brand px-6 py-[18px] text-scenario font-semibold text-white shadow-card-focus"
            >
              Comecar
            </button>
          </>
        )}
      </div>
    </div>
  );
}
