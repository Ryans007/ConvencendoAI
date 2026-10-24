import { describe, expect, it } from "vitest";

import { speakingLabel, waitingLabel } from "./speakingLabel";

describe("speakingLabel", () => {
  it("diz o nome de quem está falando", () => {
    expect(speakingLabel("James")).toBe("James está falando...");
  });

  it("usa o texto geral quando o nome não veio", () => {
    expect(speakingLabel(null)).toBe("A persona está falando...");
  });
});

describe("waitingLabel", () => {
  it("diz que a persona anunciada está pensando, e não falando", () => {
    expect(waitingLabel("Rachel", true)).toBe("Rachel está pensando...");
  });

  it("sem nome, depois da fala do aluno, diz que a resposta está a caminho", () => {
    expect(waitingLabel(null, true)).toBe("Pensando na resposta...");
  });

  it("sem nome, na abertura da sessão, diz que a cena está sendo preparada", () => {
    expect(waitingLabel(null, false)).toBe("Preparando a cena...");
  });
});
