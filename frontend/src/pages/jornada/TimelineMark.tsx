import type { ScenarioMark } from "./journeyView";

interface TimelineMarkProps {
  mark: ScenarioMark;
}

const MARK_LABEL: Record<ScenarioMark, string> = {
  locked: "Bloqueado",
  passed: "Aprovado",
  attempted: "Tentou e ainda não passou",
  available: "Disponível",
};

const MARK_STYLE: Record<ScenarioMark, string> = {
  locked: "border-line bg-line-strong text-ink-disabled",
  passed: "border-brand bg-brand text-white",
  attempted: "border-warn bg-warn-soft text-warn-strong",
  available: "border-brand bg-surface text-brand-strong",
};

function MarkGlyph({ mark }: TimelineMarkProps) {
  if (mark === "passed") {
    return <span className="text-[13px] font-bold leading-none">✓</span>;
  }
  if (mark === "attempted") {
    return <span className="text-[13px] font-bold leading-none">!</span>;
  }
  if (mark === "locked") {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
        <rect x="2.5" y="5.5" width="7" height="5" rx="1.2" />
        <path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" />
      </svg>
    );
  }
  return <span className="h-2 w-2 rounded-pill bg-brand" />;
}

/** Marca de estado de um cenário na linha do tempo, com o nome do estado para leitores de tela. */
export function TimelineMark({ mark }: TimelineMarkProps) {
  return (
    <span
      role="img"
      aria-label={MARK_LABEL[mark]}
      className={`flex h-7 w-7 flex-none items-center justify-center rounded-pill border-2 ${MARK_STYLE[mark]}`}
    >
      <MarkGlyph mark={mark} />
    </span>
  );
}
