interface LogoProps {
  size?: number;
}

/** Marca do ConvencendoAI, no tamanho pedido por quem a usa. */
export function Logo({ size = 24 }: LogoProps) {
  return (
    <img
      src="/logo.png"
      alt="ConvencendoAI"
      width={size}
      height={size}
      className="block object-contain"
    />
  );
}
