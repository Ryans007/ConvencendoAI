const SAME_ORIGIN_API_BASE_URL = "/api";

/** Parte da página que define o endereço: o protocolo e o host (com porta). */
export type PageLocation = Pick<Location, "protocol" | "host">;

/**
 * Endereço base da API: o configurado no build, ou `/api` na própria origem.
 *
 * Em produção o frontend, a API e a sessão de voz respondem no mesmo endereço, atrás do
 * mesmo proxy; só o desenvolvimento configura outro, porque a API roda em outra porta.
 */
export function resolveApiBaseUrl(configured: string | undefined): string {
  return configured || SAME_ORIGIN_API_BASE_URL;
}

/**
 * Endereço base da sessão de voz: o configurado no build, ou `/ws` no mesmo host da página.
 *
 * Usa `wss://` quando a página veio por HTTPS e `ws://` caso contrário, porque o navegador
 * recusa uma conexão insegura partindo de uma página segura.
 */
export function resolveWsBaseUrl(configured: string | undefined, location: PageLocation): string {
  if (configured) return configured;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws`;
}
