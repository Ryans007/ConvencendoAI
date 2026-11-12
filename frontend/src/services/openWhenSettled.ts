/**
 * Cria a sessao so depois de o efeito da tela se firmar, e devolve o que desfaz tudo.
 *
 * Em desenvolvimento o React monta o efeito, desmonta e monta de novo, de forma sincrona. Abrir
 * a conexao no primeiro passo gerava uma conexao descartavel, que o servidor ja tinha comecado
 * a tratar quando a segunda chegava. Adiar a criacao para o proximo ciclo faz o primeiro passo
 * ser desfeito antes de abrir qualquer coisa: so a montagem que fica abre a conexao.
 *
 * `onOpen` recebe a sessao recem-criada e devolve a funcao que desfaz o que ele ligou a ela.
 */
export function openWhenSettled<T extends { dispose(): void }>(
  create: () => T,
  onOpen: (session: T) => () => void,
): () => void {
  let session: T | null = null;
  let release: () => void = () => undefined;
  const timer = setTimeout(() => {
    session = create();
    release = onOpen(session);
  }, 0);

  return () => {
    clearTimeout(timer);
    release();
    session?.dispose();
  };
}
