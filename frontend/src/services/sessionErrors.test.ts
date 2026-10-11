import { describe, expect, it } from "vitest";

import { sessionErrorMessage } from "./sessionErrors";

const GENERIC = "Algo deu errado durante a sessão. Volte para a jornada e tente de novo.";

describe("sessionErrorMessage", () => {
  it("diz que o serviço atingiu o limite de uso quando o provedor recusa", () => {
    expect(sessionErrorMessage("provider_rate_limited")).toBe(
      "O serviço de IA atingiu o limite de uso por agora. Tente de novo em alguns minutos.",
    );
  });

  it("diz que o serviço está indisponível quando o provedor não responde", () => {
    expect(sessionErrorMessage("provider_unavailable")).toBe(
      "O serviço de IA está indisponível no momento. Tente de novo em alguns minutos.",
    );
  });

  it("diz que o cenário ainda não está liberado", () => {
    expect(sessionErrorMessage("scenario_locked")).toBe(
      "Este cenário ainda não está liberado. Conclua o anterior na jornada para abrir este.",
    );
  });

  it("diz em horas e minutos quando o nível volta, a partir do tempo do servidor", () => {
    expect(sessionErrorMessage("level_in_cooldown", 10 * 3600 + 5 * 60)).toBe(
      "Este nível volta a ficar disponível em 10 horas e 5 minutos.",
    );
  });

  it("usa o singular e omite a unidade zerada no tempo do nível", () => {
    expect(sessionErrorMessage("level_in_cooldown", 3600)).toBe(
      "Este nível volta a ficar disponível em 1 hora.",
    );
    expect(sessionErrorMessage("level_in_cooldown", 60)).toBe(
      "Este nível volta a ficar disponível em 1 minuto.",
    );
  });

  it("arredonda para cima os segundos que sobram no tempo do nível", () => {
    expect(sessionErrorMessage("level_in_cooldown", 61)).toBe(
      "Este nível volta a ficar disponível em 2 minutos.",
    );
  });

  it("sem o tempo, diz só que o nível ainda está em intervalo", () => {
    expect(sessionErrorMessage("level_in_cooldown")).toBe(
      "Este nível ainda está no intervalo entre tentativas. Volte um pouco mais tarde.",
    );
  });

  it("diz que já existe outra sessão aberta", () => {
    expect(sessionErrorMessage("session_already_open")).toBe(
      "Você já tem uma sessão aberta em outra aba ou dispositivo. Feche a outra e tente de novo.",
    );
  });

  it("diz que o limite de sessões do dia foi atingido", () => {
    expect(sessionErrorMessage("daily_session_limit")).toBe(
      "Você atingiu o limite de sessões de hoje. Volte amanhã para continuar praticando.",
    );
  });

  it("diz que a sessão foi concluída mas o relatório não saiu", () => {
    expect(sessionErrorMessage("report_failed")).toBe(
      "Você concluiu a sessão, mas não foi possível gerar o relatório agora. Tente de novo mais tarde.",
    );
  });

  it("usa o texto genérico para o código inesperado, o desconhecido e o ausente", () => {
    expect(sessionErrorMessage("unexpected")).toBe(GENERIC);
    expect(sessionErrorMessage("um_codigo_que_nao_existe")).toBe(GENERIC);
    expect(sessionErrorMessage(null)).toBe(GENERIC);
    expect(sessionErrorMessage(undefined)).toBe(GENERIC);
  });
});
