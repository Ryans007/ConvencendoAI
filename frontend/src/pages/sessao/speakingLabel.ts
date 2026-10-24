/** O que a tela diz enquanto uma persona fala: o nome dela, ou um texto geral se o nome não veio. */
export function speakingLabel(speakerName: string | null): string {
  return speakerName ? `${speakerName} está falando...` : "A persona está falando...";
}

/**
 * O que a tela diz enquanto a resposta ainda está sendo preparada e ninguém está falando: o
 * nome de quem vai responder, quando o servidor já o anunciou. Sem nome, a abertura da sessão
 * diz que a cena está sendo preparada e as demais esperas dizem que a resposta está a caminho.
 */
export function waitingLabel(speakerName: string | null, studentHasSpoken: boolean): string {
  if (speakerName) {
    return `${speakerName} está pensando...`;
  }
  return studentHasSpoken ? "Pensando na resposta..." : "Preparando a cena...";
}
