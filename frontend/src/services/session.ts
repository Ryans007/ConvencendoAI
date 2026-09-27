import { post } from "../api/client";

const REFRESH_STORAGE_KEY = "convencendoai.refreshToken";

interface TokenPair {
  access: string;
  refresh: string;
}

type Listener = () => void;

let accessToken: string | null = null;
let refreshToken: string | null = readStoredRefreshToken();
const listeners = new Set<Listener>();

function readStoredRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Grava ou apaga o token de renovacao no `localStorage`. Em ambiente sem `localStorage`
 * (aba privada bloqueando dado de site), a falha e ignorada e a sessao dura so a aba
 * atual.
 */
function persistRefreshToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(REFRESH_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(REFRESH_STORAGE_KEY);
    }
  } catch {
    return;
  }
}

/**
 * Estado de sessao do aluno.
 *
 * O token de acesso vive so em memoria (nunca persistido) porque tem o maior alcance:
 * qualquer chamada protegida aceita ele sozinho. O token de renovacao fica em
 * `localStorage`, para a sessao sobreviver ao fechamento do navegador — o backend emite
 * os dois tokens no corpo da resposta, nao em cookie, e mudar isso e trabalho de backend
 * fora do escopo deste modulo. Rotacao e blacklist do token de renovacao, ja aplicadas
 * pelo backend a cada renovacao, limitam o estrago de um token de renovacao vazado.
 */
function setTokens(pair: TokenPair | null): void {
  accessToken = pair?.access ?? null;
  refreshToken = pair?.refresh ?? null;
  persistRefreshToken(refreshToken);
  for (const listener of listeners) {
    listener();
  }
}

/** Assina mudancas de sessao (login, registro, renovacao, logout). Devolve o cancelamento. */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Token de acesso atual, se houver. Nunca persistido entre recarregamentos da aba. */
export function getAccessToken(): string | null {
  return accessToken;
}

/** Se ha uma sessao (token de acesso valido, ou ao menos um token de renovacao para tentar). */
export function isAuthenticated(): boolean {
  return accessToken !== null || refreshToken !== null;
}

/** Cria a conta e ja autentica, sem exigir login separado. */
export async function register(username: string, password: string): Promise<void> {
  const pair = await post<TokenPair>(
    "/auth/register/",
    { username, password },
    { skipAuth: true },
  );
  setTokens(pair);
}

/** Autentica com usuario e senha existentes. */
export async function login(username: string, password: string): Promise<void> {
  const pair = await post<TokenPair>("/auth/token/", { username, password }, { skipAuth: true });
  setTokens(pair);
}

/** Troca o token de renovacao guardado por um par novo. Devolve se deu certo. */
export async function refresh(): Promise<boolean> {
  if (!refreshToken) {
    return false;
  }
  try {
    const pair = await post<TokenPair>(
      "/auth/token/refresh/",
      { refresh: refreshToken },
      { skipAuth: true },
    );
    setTokens(pair);
    return true;
  } catch {
    setTokens(null);
    return false;
  }
}

/** Restaura a sessao ao carregar a aba, usando o token de renovacao persistido, se houver. */
export async function bootstrap(): Promise<void> {
  if (refreshToken) {
    await refresh();
  }
}

/** Bloqueia o token de renovacao no backend e descarta a sessao local, mesmo se a chamada falhar. */
export async function logout(): Promise<void> {
  const tokenToBlock = refreshToken;
  if (tokenToBlock) {
    await post("/auth/logout/", { refresh: tokenToBlock }).catch(() => undefined);
  }
  setTokens(null);
}
