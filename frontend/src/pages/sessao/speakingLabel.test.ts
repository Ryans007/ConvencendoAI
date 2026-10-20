import { describe, expect, it } from "vitest";

import { speakingLabel } from "./speakingLabel";

describe("speakingLabel", () => {
  it("diz o nome de quem está falando", () => {
    expect(speakingLabel("James")).toBe("James está falando...");
  });

  it("usa o texto geral quando o nome não veio", () => {
    expect(speakingLabel(null)).toBe("A persona está falando...");
  });
});
