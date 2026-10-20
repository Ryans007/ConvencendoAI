import { describe, expect, it } from "vitest";

import { endActionState } from "./endAction";

describe("pages/sessao/endAction", () => {
  it("nao aparece antes da primeira resposta do aluno", () => {
    expect(endActionState("student-turn", false)).toBe("hidden");
    expect(endActionState("persona-speaking", false)).toBe("hidden");
  });

  it("fica disponivel na vez do aluno depois que ele respondeu", () => {
    expect(endActionState("student-turn", true)).toBe("available");
  });

  it("fica desabilitada enquanto a persona fala ou o aluno grava", () => {
    expect(endActionState("persona-speaking", true)).toBe("disabled");
    expect(endActionState("recording", true)).toBe("disabled");
  });

  it("some quando a cena termina, a conexao cai ou a sessao falha", () => {
    for (const phase of ["connecting", "evaluating", "ended", "left", "connection-lost", "error"] as const) {
      expect(endActionState(phase, true)).toBe("hidden");
    }
  });
});
