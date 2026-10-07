export type NavItemId = "journey" | "review";

/**
 * Item do menu que corresponde à tela aberta. O briefing de um cenário pertence à Jornada,
 * e o relatório não pertence a nenhum item: o aluno chega nele pela nota, não pelo menu.
 */
export function activeNavItem(pathname: string): NavItemId | null {
  if (/^\/(jornada|cenario)(\/|$)/.test(pathname)) {
    return "journey";
  }
  if (/^\/revisao(\/|$)/.test(pathname)) {
    return "review";
  }
  return null;
}
