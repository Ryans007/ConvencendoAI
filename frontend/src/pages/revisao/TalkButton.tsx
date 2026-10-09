import type { KeyboardEvent, PointerEvent } from "react";

interface TalkButtonProps {
  recording: boolean;
  onStart: () => void;
  onStop: () => void;
}

/**
 * Botão de segurar para falar: gravar enquanto está pressionado e enviar ao soltar.
 *
 * Funciona com o ponteiro (mouse e toque) e com o teclado: a barra de espaço e o Enter
 * começam a gravar ao descer e enviam ao subir. Sair com o ponteiro de cima do botão também
 * envia, para a gravação nunca ficar presa. O menu de contexto é bloqueado porque o toque
 * longo do celular o abriria no meio da fala.
 */
export function TalkButton({ recording, onStart, onStop }: TalkButtonProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== " " && event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    if (!event.repeat) {
      onStart();
    }
  }

  function handleKeyUp(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== " " && event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    onStop();
  }

  return (
    <div className="flex flex-col items-center gap-4 py-1">
      <div className="relative flex h-[136px] w-[136px] items-center justify-center">
        {recording && (
          <span
            aria-hidden="true"
            className="absolute -inset-1.5 animate-ping rounded-pill border-2 border-brand"
          />
        )}
        <button
          type="button"
          aria-label={recording ? "Gravando. Solte para enviar." : "Segure para falar"}
          aria-pressed={recording}
          onPointerDown={(event: PointerEvent<HTMLButtonElement>) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            onStart();
          }}
          onPointerUp={onStop}
          onPointerCancel={onStop}
          onKeyDown={handleKeyDown}
          onKeyUp={handleKeyUp}
          onContextMenu={(event) => event.preventDefault()}
          className={`relative flex h-[136px] w-[136px] touch-none select-none items-center justify-center rounded-pill transition-[transform,box-shadow,background-color] duration-150 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-strong ${
            recording
              ? "scale-95 bg-brand-strong shadow-[0_0_0_10px_rgb(0_214_143/0.14),0_10px_30px_rgb(0_214_143/0.34)]"
              : "bg-brand shadow-[0_8px_26px_rgb(0_214_143/0.26)]"
          }`}
        >
          <svg
            width="34"
            height="34"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#FFFFFF"
            strokeWidth="1.8"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <rect x="9" y="2.5" width="6" height="11" rx="3" />
            <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" />
            <path d="M12 18v3.5" />
          </svg>
        </button>
      </div>
      <span className={`text-score font-medium ${recording ? "text-brand-strong" : "text-ink-muted"}`}>
        {recording ? "Solte para enviar" : "Segure para falar"}
      </span>
    </div>
  );
}
