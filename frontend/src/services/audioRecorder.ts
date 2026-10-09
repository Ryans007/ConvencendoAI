/** Uma gravação terminada: o áudio e quanto tempo ela durou. */
export interface Recording {
  blob: Blob;
  durationMs: number;
}

/**
 * Duração mínima de uma gravação para valer como fala. Abaixo disso, o arquivo sai com poucos
 * bytes e sem áudio de verdade: o reconhecimento de voz o recusa como arquivo inválido.
 */
export const MIN_RECORDING_MS = 350;

const DEFAULT_MIME_TYPE = "audio/webm";

/**
 * Gravador de voz do microfone, compartilhado pela sessão ao vivo e pela revisão.
 *
 * Guarda só a gravação em curso: `start` pede o microfone e começa, `stop` termina e entrega o
 * áudio, e `release` solta o microfone sem entregar nada. O tempo gravado vai junto do áudio
 * porque cada tela decide o que fazer com uma gravação curta, e a duração mínima que vale como
 * fala é `MIN_RECORDING_MS`.
 *
 * O microfone leva um instante para abrir, e o aluno pode soltar o botão nesse intervalo.
 * Soltar antes de abrir cancela a gravação: o microfone é solto assim que abre, em vez de
 * começar a gravar sem ninguém segurando o botão. Um segundo `start` enquanto o gravador está
 * ocupado é ignorado, porque abriria um segundo microfone que ninguém fecharia.
 */
export class AudioRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;
  private starting = false;
  private cancelled = false;

  /** O gravador está ocupado: abrindo o microfone ou gravando. */
  get active(): boolean {
    return this.starting || this.recorder !== null;
  }

  /**
   * Pede o microfone e começa a gravar. Devolve `false` quando não começou: já havia uma
   * gravação, ou o aluno soltou o botão antes de o microfone abrir. Falha se o aluno negar a
   * permissão.
   */
  async start(): Promise<boolean> {
    if (this.active) {
      return false;
    }
    this.starting = true;
    this.cancelled = false;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (this.cancelled) {
        this.release();
        return false;
      }
      this.chunks = [];
      this.recorder = new MediaRecorder(this.stream);
      this.recorder.ondataavailable = (event) => this.chunks.push(event.data);
      this.startedAt = Date.now();
      this.recorder.start();
      return true;
    } catch (error) {
      this.release();
      throw error;
    } finally {
      this.starting = false;
    }
  }

  /**
   * Termina a gravação e solta o microfone. Sem gravação em curso, devolve `null`. Se o
   * microfone ainda está abrindo, cancela a gravação que ia começar e também devolve `null`.
   */
  stop(): Promise<Recording | null> {
    if (this.starting) {
      this.cancelled = true;
      return Promise.resolve(null);
    }
    const recorder = this.recorder;
    if (!recorder || recorder.state === "inactive") {
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      recorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: recorder.mimeType || DEFAULT_MIME_TYPE });
        const durationMs = Date.now() - this.startedAt;
        this.release();
        resolve({ blob, durationMs });
      };
      recorder.stop();
    });
  }

  /** Solta o microfone, por exemplo ao desmontar a tela no meio de uma gravação. */
  release(): void {
    if (this.starting) {
      this.cancelled = true;
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
  }
}
