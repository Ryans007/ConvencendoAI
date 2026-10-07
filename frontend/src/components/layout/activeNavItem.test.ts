import { describe, expect, it } from "vitest";

import { activeNavItem } from "./activeNavItem";

describe("activeNavItem", () => {
  it("marca a Jornada na própria jornada", () => {
    expect(activeNavItem("/jornada")).toBe("journey");
  });

  it("marca a Jornada no briefing de um cenário", () => {
    expect(activeNavItem("/cenario/entrevista-de-emprego/2")).toBe("journey");
  });

  it("marca a Revisão na tela de revisão", () => {
    expect(activeNavItem("/revisao")).toBe("review");
  });

  it("não marca nenhum item no relatório", () => {
    expect(activeNavItem("/relatorio/42")).toBeNull();
  });

  it("não confunde caminhos que só começam parecido", () => {
    expect(activeNavItem("/jornadas")).toBeNull();
    expect(activeNavItem("/revisaozinha")).toBeNull();
  });
});
