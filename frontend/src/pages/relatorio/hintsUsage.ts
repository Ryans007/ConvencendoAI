/**
 * Frase do relatorio sobre as dicas, ou `null` quando o aluno nao ligou as dicas na
 * sessao: sem a opcao ligada, falar de dicas so confundiria.
 */
export function hintsUsageText(hintsEnabled: boolean, hintsUsed: number): string | null {
  if (!hintsEnabled) {
    return null;
  }
  if (hintsUsed === 0) {
    return "Você não usou nenhuma dica.";
  }
  if (hintsUsed === 1) {
    return "Você usou 1 dica.";
  }
  return `Você usou ${hintsUsed} dicas.`;
}
