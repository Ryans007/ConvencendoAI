interface AvatarPlaceholderProps {
  size?: number;
}

/**
 * Retrato de uma pessoa (aluno ou persona) quando nao ha foto — nenhuma API deste
 * sistema devolve foto de persona, so nome e funcao na cena, entao este e o unico
 * estado que esse avatar tem.
 */
export function AvatarPlaceholder({ size = 40 }: AvatarPlaceholderProps) {
  return (
    <div
      style={{ width: size, height: size }}
      className="flex-shrink-0 overflow-hidden rounded-pill border border-line bg-line-strong"
    >
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
        <circle cx="16" cy="12" r="6" fill="#A9B4C2" />
        <circle cx="16" cy="30" r="10" fill="#A9B4C2" />
      </svg>
    </div>
  );
}
