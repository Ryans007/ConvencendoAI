const GENERIC_SESSION_ERROR = "Algo deu errado durante a sessão. Volte para a jornada e tente de novo.";

const SESSION_ERROR_MESSAGES: Record<string, string> = {
  provider_rate_limited:
    "O serviço de IA atingiu o limite de uso por agora. Tente de novo em alguns minutos.",
  provider_unavailable:
    "O serviço de IA está indisponível no momento. Tente de novo em alguns minutos.",
  session_already_open:
    "Você já tem uma sessão aberta em outra aba ou dispositivo. Feche a outra e tente de novo.",
  daily_session_limit:
    "Você atingiu o limite de sessões de hoje. Volte amanhã para continuar praticando.",
  scenario_locked:
    "Este cenário ainda não está liberado. Conclua o anterior na jornada para abrir este.",
  report_failed:
    "Você concluiu a sessão, mas não foi possível gerar o relatório agora. Tente de novo mais tarde.",
};

/**
 * Mensagem que o aluno lê quando o servidor encerra a sessão com um aviso de erro. O
 * servidor só manda um código estável, nunca o texto técnico do provedor, e quem escolhe o
 * texto é a tela. Código ausente ou desconhecido cai no texto genérico.
 */
export function sessionErrorMessage(
  code: string | null | undefined,
  retryAfterSeconds?: number | null,
): string {
  if (!code) {
    return GENERIC_SESSION_ERROR;
  }
  if (code === LEVEL_IN_COOLDOWN_CODE) {
    return cooldownMessage(retryAfterSeconds);
  }
  return SESSION_ERROR_MESSAGES[code] ?? GENERIC_SESSION_ERROR;
}

const LEVEL_IN_COOLDOWN_CODE = "level_in_cooldown";
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;

/** Diz que o nivel esta em intervalo e, quando o servidor informa, em quanto tempo ele volta. */
function cooldownMessage(retryAfterSeconds: number | null | undefined): string {
  if (typeof retryAfterSeconds !== "number" || retryAfterSeconds <= 0) {
    return "Este nível ainda está no intervalo entre tentativas. Volte um pouco mais tarde.";
  }
  const totalMinutes = Math.ceil(retryAfterSeconds / SECONDS_PER_MINUTE);
  const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);
  const minutes = totalMinutes % MINUTES_PER_HOUR;
  const parts = [
    hours > 0 ? `${hours} ${hours === 1 ? "hora" : "horas"}` : null,
    minutes > 0 ? `${minutes} ${minutes === 1 ? "minuto" : "minutos"}` : null,
  ].filter(Boolean);
  return `Este nível volta a ficar disponível em ${parts.join(" e ")}.`;
}
