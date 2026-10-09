import { getAccessToken, refresh } from "../services/session";

const DEFAULT_BASE_URL = "http://localhost:8010/api";

const baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL;

/** Falha em uma chamada a API, com o status e o corpo desserializado quando houve resposta. */
export class ApiError extends Error {
  readonly status: number | null;
  readonly body: unknown;

  constructor(message: string, status: number | null = null, body: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions {
  signal?: AbortSignal;
  /** Chamada de autenticacao (login, registro, renovacao): nunca leva o header nem tenta renovar. */
  skipAuth?: boolean;
  /** Como ler o corpo da resposta: JSON (padrao) ou binario, como o audio da revisao. */
  responseType?: "json" | "blob";
}

async function parseErrorBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Cliente HTTP unico do frontend.
 *
 * Toda chamada de rede passa por aqui. Componentes visuais nunca falam com a rede
 * diretamente: eles consomem hooks, que consomem os modulos de `api/`.
 */
async function request<T>(
  method: "GET" | "POST",
  path: string,
  body: unknown,
  options: RequestOptions,
  retrying = false,
): Promise<T> {
  const isForm = body instanceof FormData;
  const headers: Record<string, string> = {
    Accept: options.responseType === "blob" ? "*/*" : "application/json",
  };
  if (body !== undefined && !isForm) {
    headers["Content-Type"] = "application/json";
  }
  if (!options.skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ApiError("Nao foi possivel alcancar a API.");
  }

  if (response.status === 401 && !options.skipAuth && !retrying) {
    const renewed = await refresh().catch(() => false);
    if (renewed) {
      return request<T>(method, path, body, options, true);
    }
  }

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    throw new ApiError(`A API respondeu ${response.status}.`, response.status, errorBody);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }
  if (options.responseType === "blob") {
    return (await response.blob()) as T;
  }
  return (await response.json()) as T;
}

/** Executa um GET e devolve o corpo desserializado. */
export function get<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>("GET", path, undefined, options);
}

/** Executa um POST e devolve o corpo desserializado. */
export function post<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return request<T>("POST", path, body, options);
}

/**
 * Envia um formulario multipart, como a gravacao de voz da revisao, e devolve o corpo
 * desserializado. O navegador define o `Content-Type` com o limite das partes.
 */
export function postForm<T>(path: string, form: FormData, options: RequestOptions = {}): Promise<T> {
  return request<T>("POST", path, form, options);
}

/** Executa um GET e devolve o corpo como binario, como o audio da forma correta. */
export function getBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  return request<Blob>("GET", path, undefined, { ...options, responseType: "blob" });
}
