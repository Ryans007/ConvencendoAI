import { describe, expect, it } from "vitest";

import { hintsUsageText } from "./hintsUsage";

describe("hintsUsageText", () => {
  it("nao fala de dicas quando o aluno nao as ligou", () => {
    expect(hintsUsageText(false, 0)).toBeNull();
  });

  it("diz quando o aluno ligou as dicas e nao usou nenhuma", () => {
    expect(hintsUsageText(true, 0)).toBe("Você não usou nenhuma dica.");
  });

  it("usa o singular para uma dica e o plural para mais", () => {
    expect(hintsUsageText(true, 1)).toBe("Você usou 1 dica.");
    expect(hintsUsageText(true, 3)).toBe("Você usou 3 dicas.");
  });
});
