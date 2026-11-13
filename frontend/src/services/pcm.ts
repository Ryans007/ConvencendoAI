const BYTES_PER_SAMPLE = 2;
const FULL_SCALE = 32768;

/**
 * Converte PCM de 16 bits (little-endian) em amostras de ponto flutuante entre -1 e 1, o formato
 * que o navegador agenda para tocar. Espera um numero par de bytes: quem recebe pedacos de tamanho
 * qualquer deve usar `PcmAssembler`, que guarda o byte que sobra.
 */
export function pcm16ToFloat32(bytes: Uint8Array): Float32Array {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const samples = new Float32Array(bytes.byteLength >> 1);
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = view.getInt16(index * BYTES_PER_SAMPLE, true) / FULL_SCALE;
  }
  return samples;
}

/**
 * Junta os pedacos de PCM de uma fala em amostras inteiras.
 *
 * O servidor ja entrega pedacos alinhados, mas um pedaco que termine no meio de uma amostra de 16
 * bits viraria estalo se fosse convertido sozinho. Por isso o byte que sobra de um pedaco fica
 * guardado e entra no inicio do seguinte, e nenhum byte e perdido nem tocado duas vezes.
 */
export class PcmAssembler {
  private carry: number | null = null;

  /** Converte o pedaco, junto do byte que sobrou do anterior, em amostras inteiras. */
  push(chunk: Uint8Array): Float32Array {
    let bytes = chunk;
    if (this.carry !== null) {
      bytes = new Uint8Array(chunk.length + 1);
      bytes[0] = this.carry;
      bytes.set(chunk, 1);
      this.carry = null;
    }
    if (bytes.length % BYTES_PER_SAMPLE === 1) {
      this.carry = bytes[bytes.length - 1];
      bytes = bytes.subarray(0, bytes.length - 1);
    }
    return pcm16ToFloat32(bytes);
  }

  /** Quantos bytes ficaram guardados esperando o pedaco seguinte (0 ou 1). */
  get pendingBytes(): number {
    return this.carry === null ? 0 : 1;
  }
}
