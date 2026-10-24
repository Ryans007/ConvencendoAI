import { ApiError, post } from "../api/client";

const REFRESH_STORAGE_KEY = "convencendoai.refreshToken";

interface TokenPair {
  access: string;
  refresh: string;
  /** So o login informa: verdadeiro quando o aluno entrou com a senha temporaria. */
  must_change_password?: boolean;
}

type Listener = () => void;

let accessToken: string | null = null;
let refreshToken: string | null = readStoredRefreshToken();
let passwordChangeRequired = false;
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
  if (pair === null) {
    passwordChangeRequired = false;
  }
  persistRefreshToken(refreshToken);
  notify();
}

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

/** Assina mudancas de sessao (login, troca de senha, renovacao, logout). Devolve o cancelamento. */
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

/** Se o aluno ainda precisa trocar a senha temporaria antes de usar o resto do app. */
export function isPasswordChangeRequired(): boolean {
  return passwordChangeRequired;
}

/**
 * Marca a troca de senha como obrigatoria. O cliente da API chama isto ao receber o 403
 * `password_change_required`, o que cobre quem recarregou a pagina: a renovacao do token
 * nao informa a pendencia, so a primeira chamada protegida recusada.
 */
export function requirePasswordChange(): void {
  if (!passwordChangeRequired) {
    passwordChangeRequired = true;
    notify();
  }
}

/** Autentica com usuario e senha existentes; a resposta diz se a troca de senha e obrigatoria. */
export async function login(username: string, password: string): Promise<void> {
  const pair = await post<TokenPair>("/auth/token/", { username, password }, { skipAuth: true });
  passwordChangeRequired = pair.must_change_password === true;
  setTokens(pair);
}

/** Troca a senha, informando a atual, e segue com os tokens novos que a API devolve. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const pair = await post<TokenPair>("/auth/password/", {
    current_password: currentPassword,
    new_password: newPassword,
  });
  passwordChangeRequired = false;
  setTokens(pair);
}

type RenewalOutcome = "renewed" | "refused" | "unreachable";

let renewalInProgress: Promise<boolean> | null = null;

/**
 * Troca o token de renovacao guardado por um par novo. Devolve se deu certo.
 *
 * Uma renovacao por vez: quando o acesso vence, varias chamadas da tela recebem 401 juntas, e
 * cada renovacao bloqueia o token usado no servidor. Quem chama enquanto uma renovacao esta em
 * andamento recebe o resultado dela, em vez de renovar de novo com o mesmo token.
 */
export function refresh(): Promise<boolean> {
  renewalInProgress ??= renewSession().finally(() => {
    renewalInProgress = null;
  });
  return renewalInProgress;
}

/**
 * Renova a sessao e decide se ela continua.
 *
 * Um token recusado pode ter sido usado por outra aba, que guardou o par novo no navegador:
 * nesse caso a aba adota o token guardado e tenta uma unica vez com ele. A sessao so e apagada
 * quando o servidor recusa o token e nao ha outro para tentar. Sem resposta do servidor (rede
 * fora do ar, erro interno), a sessao fica como esta, para uma queda passageira nao deslogar.
 */
async function renewSession(): Promise<boolean> {
  const used = refreshToken;
  if (!used) {
    return false;
  }
  const outcome = await renewWith(used);
  if (outcome !== "refused") {
    return outcome === "renewed";
  }
  const stored = readStoredRefreshToken();
  if (stored && stored !== used) {
    const retry = await renewWith(stored);
    if (retry !== "refused") {
      return retry === "renewed";
    }
  }
  setTokens(null);
  return false;
}

async function renewWith(token: string): Promise<RenewalOutcome> {
  try {
    const pair = await post<TokenPair>("/auth/token/refresh/", { refresh: token }, { skipAuth: true });
    setTokens(pair);
    return "renewed";
  } catch (error) {
    return isRefusal(error) ? "refused" : "unreachable";
  }
}

/** Se o servidor recusou o token, e nao apenas deixou de responder ou falhou por dentro. */
function isRefusal(error: unknown): boolean {
  return !(error instanceof ApiError) || (error.status !== null && error.status < 500);
}

/** Restaura a sessao ao carregar a aba, usando o token de renovacao persistido, se houver. */
export async function bootstrap(): Promise<void> {
  if (refreshToken) {
    await refresh();
  }
}

/**
 * Descarta a sessao local sem chamar o backend. O cliente da API usa quando a renovacao
 * funcionou mas o token novo continua recusado: o servidor nao aceita mais essa sessao,
 * entao o aluno volta a Entrada em vez de ficar preso numa tela com erro.
 */
export function endSession(): void {
  setTokens(null);
}

/** Bloqueia o token de renovacao no backend e descarta a sessao local, mesmo se a chamada falhar. */
export async function logout(): Promise<void> {
  const tokenToBlock = refreshToken;
  if (tokenToBlock) {
    await post("/auth/logout/", { refresh: tokenToBlock }).catch(() => undefined);
  }
  setTokens(null);
}
