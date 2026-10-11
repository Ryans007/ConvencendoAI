/**
 * Confere o formulario de definir a senha antes de enviar, para nao gastar uma chamada em
 * erro que a tela ja enxerga. As regras de forca da senha ficam so no backend, que devolve
 * o motivo; aqui so o que depende dos tres campos juntos.
 */
export function validatePasswordForm(
  currentPassword: string,
  newPassword: string,
  confirmation: string,
): string | null {
  if (!currentPassword || !newPassword || !confirmation) {
    return "Preencha os tres campos.";
  }
  if (newPassword !== confirmation) {
    return "A confirmacao nao e igual a senha nova.";
  }
  if (newPassword === currentPassword) {
    return "A senha nova nao pode ser igual a temporaria.";
  }
  return null;
}
