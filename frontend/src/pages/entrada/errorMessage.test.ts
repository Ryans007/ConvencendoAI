import { describe, expect, it } from "vitest";

import { ApiError } from "../../api/client";
import { authErrorMessage } from "./errorMessage";

function locked(seconds?: number): ApiError {
  return new ApiError("A API respondeu 429.", 429, {
    code: "login_locked",
    ...(seconds === undefined ? {} : { retry_after_seconds: seconds }),
  });
}

describe("authErrorMessage", () => {
  it("avisa em quantos minutos o aluno pode tentar de novo, arredondando para cima", () => {
    expect(authErrorMessage(locked(721))).toBe(
      "Muitas tentativas de login. Tente de novo em 13 minutos.",
    );
  });

  it("usa o singular quando falta um minuto ou menos", () => {
    expect(authErrorMessage(locked(30))).toBe(
      "Muitas tentativas de login. Tente de novo em 1 minuto.",
    );
  });

  it("cai num texto geral quando o tempo nao vem", () => {
    expect(authErrorMessage(locked())).toBe(
      "Muitas tentativas de login. Tente de novo em alguns minutos.",
    );
  });

  it("nao diz se o usuario existe: o erro de credencial segue generico", () => {
    const error = new ApiError("A API respondeu 401.", 401, { detail: "Credenciais invalidas." });
    expect(authErrorMessage(error)).toBe("Credenciais invalidas.");
  });

  it("sem resposta da API, avisa que nao alcancou o servidor", () => {
    expect(authErrorMessage(new Error("rede"))).toMatch(/alcançar o servidor|alcancar o servidor/);
  });
});
