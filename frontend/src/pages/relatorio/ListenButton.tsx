interface ListenButtonProps {
  playing: boolean;
  disabled: boolean;
  onListen: () => void;
}

/** Botão "Ouvir" da forma correta, com o mesmo visual do "Ouvir" da revisão. */
export default function ListenButton({ playing, disabled, onListen }: ListenButtonProps) {
  return (
    <button
      type="button"
      onClick={onListen}
      disabled={disabled}
      aria-label="Ouvir a frase correta em inglês"
      className="inline-flex items-center gap-2 rounded-pill border border-brand-line bg-surface px-3.5 py-2 text-aux font-semibold text-brand-strong hover:border-brand disabled:cursor-default"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M2.5 6h2.5l3.5-3v10L5 10H2.5z" />
        <path d="M11 5.5a3.5 3.5 0 0 1 0 5" />
        <path d="M12.8 3.6a6 6 0 0 1 0 8.8" />
      </svg>
      <span>{playing ? "Tocando…" : "Ouvir"}</span>
    </button>
  );
}
