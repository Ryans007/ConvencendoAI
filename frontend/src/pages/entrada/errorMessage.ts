import { ApiError, apiErrorCode } from "../../api/client";

const LOGIN_LOCKED_CODE = "login_locked";
const SECONDS_PER_MINUTE = 60;

/** Extrai uma mensagem unica e legivel do corpo de erro devolvido pela API de autenticacao. */
export function authErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Nao foi possivel alcancar o servidor. Tente novamente.";
  }

  if (apiErrorCode(error) === LOGIN_LOCKED_CODE) {
    return lockedMessage(error.body);
  }

  const body = error.body;
  if (body && typeof body === "object") {
    const fields = body as Record<string, unknown>;
    for (const key of ["username", "password", "current_password", "new_password", "detail"]) {
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

/** Avisa que houve tentativas demais e em quantos minutos o aluno pode tentar de novo. */
function lockedMessage(body: unknown): string {
  const seconds = (body as { retry_after_seconds?: unknown }).retry_after_seconds;
  if (typeof seconds !== "number" || seconds <= 0) {
    return "Muitas tentativas de login. Tente de novo em alguns minutos.";
  }
  const minutes = Math.ceil(seconds / SECONDS_PER_MINUTE);
  return `Muitas tentativas de login. Tente de novo em ${minutes} ${minutes === 1 ? "minuto" : "minutos"}.`;
}
