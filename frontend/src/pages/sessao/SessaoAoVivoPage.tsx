import { useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { AvatarPlaceholder } from "../../components/AvatarPlaceholder";
import { LogoutLink } from "../../components/LogoutLink";
import { useLiveSession } from "../../hooks/useLiveSession";
import type { ReportContext } from "../relatorio/reportContext";

const ENDED_TRANSITION_MS = 1400;
const GENERIC_ERROR_MESSAGE =
  "Algo deu errado durante a sessão. Volte para a jornada e tente de novo.";

/**
 * Tela de sessao ao vivo: o aluno fala com as personas em tempo real, um turno por vez.
 *
 * Em caso de erro, o motivo tecnico vai so para o console, para quem esta depurando — o
 * aluno ve apenas a mensagem generica.
 */
export default function SessaoAoVivoPage() {
  const { scenarioSlug = "", levelOrder = "" } = useParams();
  const level = Number(levelOrder);
  const navigate = useNavigate();
  const location = useLocation();
  const navState = location.state as { maxTurns?: number; reportContext?: ReportContext } | null;
  const maxTurns = navState?.maxTurns ?? null;
  const reportContext = navState?.reportContext;

  const session = useLiveSession(scenarioSlug, level);
  const { phase, turnCount, errorMessage, result, noSpeechNotice, startRecording, stopRecording, leaveEarly } =
    session;

  useEffect(() => {
    if (phase !== "ended" || !result) {
      return;
    }
    const timer = setTimeout(() => {
      navigate(`/relatorio/${result.attemptId}`, { replace: true, state: { reportContext } });
    }, ENDED_TRANSITION_MS);
    return () => clearTimeout(timer);
  }, [phase, result, navigate, reportContext]);

  useEffect(() => {
    if (phase === "left") {
      navigate("/jornada", { replace: true });
    }
  }, [phase, navigate]);

  useEffect(() => {
    if (phase === "error" && errorMessage) {
      console.error("Sessao ao vivo encerrada por erro:", errorMessage);
    }
  }, [phase, errorMessage]);

  const personaSpeaking = phase === "persona-speaking";
  const studentTurn = phase === "student-turn" || phase === "recording";
  const recording = phase === "recording";

  return (
    <div className="relative flex min-h-screen flex-col bg-app">
      <div className="flex items-center justify-between gap-6 px-8 py-7">
        <button
          type="button"
          onClick={leaveEarly}
          className="text-aux text-ink-muted hover:text-ink"
          disabled={phase === "connecting" || phase === "ended"}
        >
          Sair
        </button>
        <span className="text-aux text-ink-muted">
          {maxTurns ? `turno ${Math.min(turnCount, maxTurns)} de ${maxTurns}` : ""}
        </span>
        <LogoutLink className="text-aux text-ink-disabled hover:text-ink-muted" />
      </div>

      {(phase === "connecting" || phase === "persona-speaking" || phase === "student-turn" || phase === "recording") && (
        <div className="flex flex-1 flex-col items-center justify-center gap-10 px-8 pb-20">
          <div className="relative flex h-28 w-28 items-center justify-center">
            {personaSpeaking && (
              <div className="absolute inset-0 animate-ping rounded-full border border-brand" />
            )}
            <AvatarPlaceholder size={88} />
          </div>

          <div className="flex min-h-[76px] flex-col items-center gap-5">
            <span className={`text-center text-[22px] font-medium ${recording ? "text-brand-strong" : "text-ink"}`}>
              {phase === "connecting" && "Conectando..."}
              {personaSpeaking && "A persona esta falando..."}
              {studentTurn && !recording && "Sua vez de falar"}
              {recording && "Gravando..."}
            </span>
            {studentTurn && !recording && noSpeechNotice && (
              <span role="status" className="text-center text-scenario text-warn-strong">
                Não consegui ouvir você. Segure o botão e fale de novo.
              </span>
            )}
          </div>

          {studentTurn && (
            <div className="flex flex-col items-center gap-[18px]">
              <button
                type="button"
                onPointerDown={startRecording}
                onPointerUp={stopRecording}
                onPointerLeave={() => recording && stopRecording()}
                onContextMenu={(event) => event.preventDefault()}
                className={`flex h-[136px] w-[136px] touch-none select-none items-center justify-center rounded-full border-none ${
                  recording ? "scale-95 bg-brand-strong shadow-card-focus" : "bg-brand shadow-card-focus"
                }`}
              >
                <span className="sr-only">Segure para falar</span>
              </button>
              <span className={`text-scenario font-medium ${recording ? "text-brand-strong" : "text-ink-muted"}`}>
                {recording ? "Solte para enviar" : "Segure para falar"}
              </span>
            </div>
          )}
        </div>
      )}

      {phase === "ended" && result && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand text-white shadow-card-focus">
            <span className="text-[26px] font-bold">&#10003;</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <span className="text-[22px] font-semibold tracking-tight">Sessao concluida!</span>
            <span className="text-scenario text-ink-muted">Preparando seu relatorio...</span>
          </div>
        </div>
      )}

      {(phase === "connection-lost" || phase === "error") && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
          <span className="text-scenario font-medium text-warn-strong">
            {phase === "connection-lost" ? "A conexão caiu antes da sessão terminar." : GENERIC_ERROR_MESSAGE}
          </span>
          <button
            type="button"
            onClick={() => navigate("/jornada", { replace: true })}
            className="rounded-pill bg-brand px-6 py-3 text-scenario font-semibold text-white"
          >
            Voltar para a jornada
          </button>
        </div>
      )}
    </div>
  );
}
