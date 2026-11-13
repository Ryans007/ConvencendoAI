import { describe, expect, it } from "vitest";

import { PcmAssembler, pcm16ToFloat32 } from "./pcm";

function pcmBytes(values: number[]): Uint8Array {
  const bytes = new Uint8Array(values.length * 2);
  const view = new DataView(bytes.buffer);
  values.forEach((value, index) => view.setInt16(index * 2, value, true));
  return bytes;
}

function collect(assembler: PcmAssembler, chunks: Uint8Array[]): number[] {
  return chunks.flatMap((chunk) => Array.from(assembler.push(chunk)));
}

describe("services/pcm", () => {
  it("converte PCM de 16 bits para ponto flutuante entre -1 e 1", () => {
    const samples = pcm16ToFloat32(pcmBytes([0, 16384, -16384, -32768, 32767]));

    expect(Array.from(samples)).toEqual([0, 0.5, -0.5, -1, 32767 / 32768]);
  });

  it("um fluxo vazio nao gera amostra", () => {
    expect(pcm16ToFloat32(new Uint8Array(0))).toHaveLength(0);
  });

  it("pedacos de tamanho par dao as mesmas amostras da conversao de uma vez", () => {
    const values = Array.from({ length: 400 }, (_, index) => (index * 97) % 30000 - 15000);
    const whole = Array.from(pcm16ToFloat32(pcmBytes(values)));
    const bytes = pcmBytes(values);

    const pieces = [bytes.slice(0, 100), bytes.slice(100, 600), bytes.slice(600)];

    expect(collect(new PcmAssembler(), pieces)).toEqual(whole);
  });

  it("pedacos de tamanho impar nao perdem nem repetem nenhum byte", () => {
    const values = Array.from({ length: 1000 }, (_, index) => (index * 37) % 30000 - 15000);
    const whole = Array.from(pcm16ToFloat32(pcmBytes(values)));
    const bytes = pcmBytes(values);
    const sizes = [701, 1203, 2001, 999, 1501];
    const pieces: Uint8Array[] = [];
    for (let start = 0, turn = 0; start < bytes.length; turn += 1) {
      pieces.push(bytes.slice(start, start + sizes[turn % sizes.length]));
      start += sizes[turn % sizes.length];
    }

    expect(collect(new PcmAssembler(), pieces)).toEqual(whole);
  });

  it("um pedaco de um byte so devolve amostra quando o proximo completa", () => {
    const assembler = new PcmAssembler();
    const bytes = pcmBytes([1000, -2000]);

    const first = assembler.push(bytes.slice(0, 1));
    const second = assembler.push(bytes.slice(1, 3));
    const third = assembler.push(bytes.slice(3));

    expect(first).toHaveLength(0);
    expect(Array.from(second)).toEqual([1000 / 32768]);
    expect(Array.from(third)).toEqual([-2000 / 32768]);
  });

  it("informa quando um byte esta guardado", () => {
    const assembler = new PcmAssembler();

    assembler.push(new Uint8Array([1, 2, 3]));

    expect(assembler.pendingBytes).toBe(1);
    assembler.push(new Uint8Array([4]));
    expect(assembler.pendingBytes).toBe(0);
  });

  it("um pedaco vazio nao muda o byte guardado", () => {
    const assembler = new PcmAssembler();
    assembler.push(new Uint8Array([9]));

    const samples = assembler.push(new Uint8Array(0));

    expect(samples).toHaveLength(0);
    expect(assembler.pendingBytes).toBe(1);
  });
});
