/** O que a tela diz enquanto uma persona fala: o nome dela, ou um texto geral se o nome não veio. */
export function speakingLabel(speakerName: string | null): string {
  return speakerName ? `${speakerName} está falando...` : "A persona está falando...";
}
