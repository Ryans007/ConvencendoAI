const SILENCE_SAMPLE_RATE = 8000;
const SILENCE_SAMPLES = 800;

/** Um WAV mono de 16 bits só de zeros, curto o bastante para não ser ouvido nem notado. */
function createSilence(): Blob {
  const dataBytes = SILENCE_SAMPLES * 2;
  const view = new DataView(new ArrayBuffer(44 + dataBytes));
  const writeText = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, SILENCE_SAMPLE_RATE, true);
  view.setUint32(28, SILENCE_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, dataBytes, true);
  return new Blob([view.buffer], { type: "audio/wav" });
}

/**
 * Player de áudio único, compartilhado por tudo que toca durante uma tela.
 *
 * O Safari do iPhone só deixa um elemento de áudio tocar sozinho se ele já foi iniciado dentro de
 * um gesto do aluno, e um elemento novo por fala nunca recebe gesto: a primeira fala toca porque
 * chega logo depois do clique que abriu a tela, e as seguintes são recusadas. Por isso há um só
 * elemento, `unlock` o inicia dentro do toque do aluno, e `play` só troca a fonte dele.
 */
export class AudioPlayer {
  private readonly element = new Audio();
  private silenceUrl: string | null = null;
  private currentUrl: string | null = null;

  /**
   * Libera o player para tocar depois, tocando um instante de silêncio. Deve ser chamado de forma
   * síncrona dentro do tratador do toque, antes de qualquer espera. Nunca falha: um erro aqui só
   * significa que o navegador não precisava da liberação.
   */
  unlock(): void {
    this.silenceUrl ??= URL.createObjectURL(createSilence());
    this.element.src = this.silenceUrl;
    this.element.play().catch(() => undefined);
  }

  /**
   * Toca o áudio e resolve quando ele termina. Rejeita com o erro original se o navegador recusar
   * tocar ou falhar ao decodificar, para quem chama decidir o que fazer. `onStart` é chamado uma
   * vez, quando o som começa a sair de fato, e não quando o pedido de reprodução é feito: entre os
   * dois há a decodificação, que faz parte do que o aluno espera.
   */
  play(blob: Blob, onStart?: () => void): Promise<void> {
    this.revokeCurrent();
    const url = URL.createObjectURL(blob);
    this.currentUrl = url;
    return new Promise((resolve, reject) => {
      const settle = (callback: () => void) => {
        this.element.onended = null;
        this.element.onerror = null;
        this.element.onplaying = null;
        callback();
      };
      this.element.onplaying = () => {
        this.element.onplaying = null;
        onStart?.();
      };
      this.element.onended = () => settle(resolve);
      this.element.onerror = () =>
        settle(() => reject(this.element.error ?? new Error("MediaError")));
      this.element.src = url;
      this.element.play().catch((cause) => settle(() => reject(cause)));
    });
  }

  private revokeCurrent(): void {
    if (this.currentUrl) {
      URL.revokeObjectURL(this.currentUrl);
      this.currentUrl = null;
    }
  }
}
