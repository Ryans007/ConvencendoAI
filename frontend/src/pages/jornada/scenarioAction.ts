/** Formata o tempo restante de cooldown de um nivel de forma legivel. */
export function formatCooldown(seconds: number): string {
  const hours = Math.ceil(seconds / 3600);
  if (hours >= 1) {
    return `Libera em ${hours}h`;
  }
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `Libera em ${minutes}min`;
}
