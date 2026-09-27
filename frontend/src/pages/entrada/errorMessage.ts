import { ApiError } from "../../api/client";

/** Extrai uma mensagem unica e legivel do corpo de erro devolvido pela API de autenticacao. */
export function authErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Nao foi possivel alcancar o servidor. Tente novamente.";
  }

  const body = error.body;
  if (body && typeof body === "object") {
    const fields = body as Record<string, unknown>;
    for (const key of ["username", "password", "detail"]) {
      const value = fields[key];
      if (Array.isArray(value) && value.length > 0) {
        return String(value[0]);
      }
      if (typeof value === "string") {
        return value;
      }
    }
  }

  return "Nao foi possivel concluir. Tente novamente.";
}
