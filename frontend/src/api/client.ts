/**
 * Cliente HTTP unico do frontend.
 *
 * Toda chamada de rede passa por aqui. Componentes visuais nunca falam com a rede
 * diretamente: eles consomem hooks, que consomem os modulos de `api/`.
 */

const DEFAULT_BASE_URL = "http://localhost:8010/api";

const baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL;

/** Falha em uma chamada a API, com o status quando houve resposta. */
export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Executa um GET e devolve o corpo desserializado.
 *
 * Trata dois casos como erro: resposta fora da faixa de sucesso, e falha de transporte
 * (servidor fora do ar, DNS, CORS). O segundo caso nao tem status.
 */
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ApiError("Nao foi possivel alcancar a API.");
  }

  if (!response.ok) {
    throw new ApiError(`A API respondeu ${response.status}.`, response.status);
  }

  return (await response.json()) as T;
}
