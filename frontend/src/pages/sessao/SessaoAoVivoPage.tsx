import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { AvatarPlaceholder } from "../../components/AvatarPlaceholder";
import { LogoutLink } from "../../components/LogoutLink";
import { useLiveSession } from "../../hooks/useLiveSession";
import { sessionErrorMessage } from "../../services/sessionErrors";
import type { ReportContext } from "../relatorio/reportContext";
import { endActionState } from "./endAction";
import { HintPanel } from "./HintPanel";
import { speakingLabel } from "./speakingLabel";

const ENDED_TRANSITION_MS = 1400;

/**
 * Tela de sessao ao vivo: o aluno fala com as personas em tempo real, um turno por vez.
 *
 * Em caso de erro, o motivo tecnico vai so para o console, para quem esta depurando — o
 * aluno ve a mensagem correspondente ao codigo do erro. Com as dicas ligadas no briefing,
 * a vez do aluno oferece a dica. Os unicos textos da sessao sao a dica e o nome de quem esta
 * falando, nunca o texto de uma fala.
 *
 * Alem de sair sem relatorio, o aluno pode encerrar a conversa e pedir o relatorio, depois da
 * primeira resposta e na vez dele, com uma confirmacao antes de valer: nenhuma persona decide o
 * fim da cena, que vem do limite de turnos ou deste pedido.
 */
export default function SessaoAoVivoPage() {
  const { scenarioSlug = "", levelOrder = "" } = useParams();
  const level = Number(levelOrder);
  const navigate = useNavigate();
  const location = useLocation();
  const navState = location.state as {
    maxTurns?: number;
    reportContext?: ReportContext;
    hintsEnabled?: boolean;
  } | null;
  const maxTurns = navState?.maxTurns ?? null;
  const reportContext = navState?.reportContext;
  const hintsEnabled = navState?.hintsEnabled ?? false;

  const session = useLiveSession(scenarioSlug, level, hintsEnabled);
  const {
    phase,
    turnCount,
    errorMessage,
    errorCode,
    errorRetryAfterSeconds,
    result,
    noSpeechNotice,
    audioTooLargeNotice,
    studentHasSpoken,
    speakerName,
    hint,
    startRecording,
    stopRecording,
    leaveEarly,
    endAndReport,
    requestHint,
  } = session;
  const [confirmingAtTurn, setConfirmingAtTurn] = useState<number | null>(null);

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
  const endAction = endActionState(phase, studentHasSpoken);
  const confirmingEnd = confirmingAtTurn === turnCount && endAction === "available";

  return (
    <div className="relative flex min-h-screen flex-col bg-app">
      <div className="flex items-center justify-between gap-6 px-8 py-7">
        <button
          type="button"
          onClick={leaveEarly}
          className="text-aux text-ink-muted hover:text-ink"
          disabled={phase === "connecting" || phase === "evaluating" || phase === "ended"}
        >
          Sair sem relatório
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
              {personaSpeaking && speakingLabel(speakerName)}
              {studentTurn && !recording && "Sua vez de falar"}
              {recording && "Gravando..."}
            </span>
            {studentTurn && !recording && audioTooLargeNotice && (
              <span role="status" className="text-center text-scenario text-warn-strong">
                Sua fala ficou longa demais. Fale uma parte de cada vez e tente de novo.
              </span>
            )}
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

          {hintsEnabled && studentTurn && (
            <HintPanel hint={hint} canRequest={!recording} onRequest={requestHint} />
          )}

          {endAction !== "hidden" &&
            (confirmingEnd ? (
              <div
                role="group"
                aria-label="Confirmar o encerramento da sessão"
                className="flex max-w-[520px] flex-col items-center gap-3 rounded-card border border-brand-line bg-brand-soft px-5 py-4 text-center"
              >
                <span className="text-scenario text-ink">
                  Sua conversa será avaliada até aqui. Quer encerrar e ver o relatório?
                </span>
                <div className="flex flex-wrap items-center justify-center gap-3">
                  <button
                    type="button"
                    autoFocus
                    onClick={endAndReport}
                    className="rounded-pill bg-brand px-5 py-2 text-scenario font-semibold text-white"
                  >
                    Encerrar e ver relatório
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingAtTurn(null)}
                    className="rounded-pill border border-brand-line px-5 py-2 text-scenario font-medium text-ink-muted hover:text-ink"
                  >
                    Continuar a conversa
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingAtTurn(turnCount)}
                disabled={endAction === "disabled"}
                className="text-aux text-ink-muted underline hover:text-ink disabled:text-ink-disabled disabled:no-underline"
              >
                Encerrar e ver relatório
              </button>
            ))}
        </div>
      )}

      {(phase === "evaluating" || (phase === "ended" && result)) && (
        <div role="status" className="flex flex-1 flex-col items-center justify-center gap-6">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand text-white shadow-card-focus">
            <span className="text-[26px] font-bold">&#10003;</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <span className="text-[22px] font-semibold tracking-tight">Sessão concluída!</span>
            <span className="text-scenario text-ink-muted">Preparando seu relatório...</span>
          </div>
        </div>
      )}

      {(phase === "connection-lost" || phase === "error") && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
          <span className="text-scenario font-medium text-warn-strong">
            {phase === "connection-lost"
              ? "A conexão caiu antes da sessão terminar."
              : sessionErrorMessage(errorCode, errorRetryAfterSeconds)}
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
