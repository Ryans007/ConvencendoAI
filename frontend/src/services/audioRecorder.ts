/** Uma gravação terminada: o áudio e quanto tempo ela durou. */
export interface Recording {
  blob: Blob;
  durationMs: number;
}

const DEFAULT_MIME_TYPE = "audio/webm";

/**
 * Gravador de voz do microfone, compartilhado pela sessão ao vivo e pela revisão.
 *
 * Guarda só a gravação em curso: `start` pede o microfone e começa, `stop` termina e entrega o
 * áudio, e `release` solta o microfone sem entregar nada. O tempo gravado vai junto do áudio
 * porque cada tela decide o que fazer com uma gravação curta: a sessão envia como está, e a
 * revisão a trata como "não consegui ouvir".
 */
export class AudioRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;

  /** Pede o microfone e começa a gravar. Falha se o aluno negar a permissão. */
  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream);
    this.recorder.ondataavailable = (event) => this.chunks.push(event.data);
    this.startedAt = Date.now();
    this.recorder.start();
  }

  /** Termina a gravação e solta o microfone. Sem gravação em curso, devolve `null`. */
  stop(): Promise<Recording | null> {
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
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
  }
}
