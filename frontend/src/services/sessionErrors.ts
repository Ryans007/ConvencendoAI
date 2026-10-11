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
  report_failed:
    "Você concluiu a sessão, mas não foi possível gerar o relatório agora. Tente de novo mais tarde.",
};

/**
 * Mensagem que o aluno lê quando o servidor encerra a sessão com um aviso de erro. O
 * servidor só manda um código estável, nunca o texto técnico do provedor, e quem escolhe o
 * texto é a tela. Código ausente ou desconhecido cai no texto genérico.
 */
export function sessionErrorMessage(code: string | null | undefined): string {
  if (!code) {
    return GENERIC_SESSION_ERROR;
  }
  return SESSION_ERROR_MESSAGES[code] ?? GENERIC_SESSION_ERROR;
}
