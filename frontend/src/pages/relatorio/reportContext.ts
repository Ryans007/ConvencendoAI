/**
 * O relatório da API só devolve o slug do cenário e o número do nível — nomes
 * legíveis (título do cenário, nome do nível) vêm do briefing, uma tela antes.
 * Esse contexto viaja de cenário -> sessão -> relatório via estado de navegação,
 * para a tela de relatório não precisar exibir o slug cru quando alcançada pelo
 * fluxo normal.
 */
export interface ReportContext {
  scenarioTitle: string;
  levelLabel: string;
  trackTitle?: string;
}

export function prettifySlug(slug: string): string {
  if (!slug) {
    return slug;
  }
  const spaced = slug.replace(/-/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
