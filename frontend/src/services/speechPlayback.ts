import { PcmAssembler } from "./pcm";

export interface AudioBufferLike {
  readonly duration: number;
  copyToChannel(source: Float32Array, channel: number): void;
}

export interface AudioSourceLike {
  buffer: AudioBufferLike | null;
  onended: (() => void) | null;
  connect(destination: unknown): void;
  start(when: number): void;
}

/** O pedaco do contexto de audio do navegador que o player usa, para poder ser trocado nos testes. */
export interface AudioContextLike {
  readonly currentTime: number;
  readonly destination: unknown;
  createBuffer(channels: number, length: number, sampleRate: number): AudioBufferLike;
  createBufferSource(): AudioSourceLike;
}

export interface SpeechFormat {
  sampleRate: number;
  channels: number;
}

export interface SpeechOutcome {
  receivedBytes: number;
  expectedBytes: number | null;
  cut: boolean;
  underruns: number;
}

export interface PlaybackOptions {
  now?: () => number;
}

const PREROLL_SECONDS = 0.4;
const MERGE_SECONDS = 0.02;
const WINDOW_START_SECONDS = 0.2;
const WINDOW_END_SECONDS = 0.8;
const MIN_REAL_TIME_RATE = 1.3;
const START_MARGIN_SECONDS = 0.04;
const RECOVERY_MARGIN_SECONDS = 0.02;
const BYTES_PER_SAMPLE = 2;

type Decision = "go" | "hold";

/**
 * Toca uma fala da persona que chega em pedacos de PCM, sem esperar a fala inteira.
 *
 * Cada pedaco vira um buffer agendado no instante exato em que o anterior termina, sem
 * temporizadores, para as emendas nao terem silencio nem estalo. A fala so comeca quando ha um
 * pequeno reservatorio e quando o ritmo em que o audio chega aguenta tocar sem parar: medido o
 * tempo que levam os audios entre 0,2 s e 0,8 s, um ritmo menor que 1,3 vezes o tempo real faz a
 * fala esperar chegar inteira, que e o comportamento de antes e nunca tem buraco. Uma fala curta,
 * que nao chega a 0,8 s, comeca ao chegar inteira.
 *
 * Os pedacos que chegam antes de `play` ficam guardados, porque a fala so pode comecar depois de
 * a anterior terminar. A fala e dada como tocada so quando o ultimo som termina, e como cortada
 * quando o total de bytes recebidos nao bate com o que o servidor declarou no fim.
 */
export class SpeechPlayback {
  private readonly assembler = new PcmAssembler();
  private readonly context: AudioContextLike;
  private readonly sampleRate: number;
  private readonly now: () => number;
  private pending: Float32Array[] = [];
  private pendingSamples = 0;
  private receivedBytes = 0;
  private expectedBytes: number | null = null;
  private ended = false;
  private aborted = false;
  private released = false;
  private started = false;
  private scheduledAny = false;
  private nextStart = 0;
  private lastSource: AudioSourceLike | null = null;
  private lastSourceEnded = false;
  private underruns = 0;
  private windowStartedAt: number | null = null;
  private decision: Decision | null = null;
  private onStart: (() => void) | null = null;
  private settle: ((outcome: SpeechOutcome) => void) | null = null;
  private settled = false;
  private result: Promise<SpeechOutcome> | null = null;

  constructor(context: AudioContextLike, format: SpeechFormat, options: PlaybackOptions = {}) {
    if (format.channels !== 1) {
      throw new Error("so audio mono e suportado no player em fluxo");
    }
    this.context = context;
    this.sampleRate = format.sampleRate;
    this.now = options.now ?? (() => performance.now());
  }

  /** Recebe o proximo pedaco de PCM da fala. */
  push(chunk: Uint8Array): void {
    this.receivedBytes += chunk.length;
    this.measureArrival();
    const samples = this.assembler.push(chunk);
    if (samples.length > 0) {
      this.pending.push(samples);
      this.pendingSamples += samples.length;
    }
    this.drive();
  }

  /** O servidor terminou a fala e informou quantos bytes mandou. */
  finish(expectedBytes: number): void {
    this.expectedBytes = expectedBytes;
    this.ended = true;
    this.drive();
  }

  /** A conexao caiu no meio da fala: toca o que ja chegou e registra a fala como cortada. */
  abort(): void {
    this.aborted = true;
    this.ended = true;
    this.drive();
  }

  /**
   * Libera a fala para tocar e devolve o resultado quando o ultimo som termina. `onStart` e
   * chamado uma vez, no instante em que o primeiro som e agendado.
   */
  play(onStart: () => void): Promise<SpeechOutcome> {
    if (this.result) {
      return this.result;
    }
    this.onStart = onStart;
    this.released = true;
    this.result = new Promise<SpeechOutcome>((resolve) => {
      this.settle = resolve;
    });
    this.drive();
    return this.result;
  }

  private measureArrival(): void {
    const reached = this.receivedBytes / (this.sampleRate * BYTES_PER_SAMPLE);
    if (this.windowStartedAt === null && reached >= WINDOW_START_SECONDS) {
      this.windowStartedAt = this.now();
    }
    if (this.decision === null && this.windowStartedAt !== null && reached >= WINDOW_END_SECONDS) {
      const elapsedSeconds = Math.max((this.now() - this.windowStartedAt) / 1000, 0.001);
      const rate = (WINDOW_END_SECONDS - WINDOW_START_SECONDS) / elapsedSeconds;
      this.decision = rate >= MIN_REAL_TIME_RATE ? "go" : "hold";
    }
  }

  private drive(): void {
    if (!this.released || this.settled) {
      return;
    }
    if (!this.started) {
      const buffered = this.pendingSamples / this.sampleRate;
      const ready = this.ended || (buffered >= PREROLL_SECONDS && this.decision === "go");
      if (!ready) {
        return;
      }
      this.started = true;
    }
    this.flush();
    this.finishIfDone();
  }

  private flush(): void {
    if (this.pendingSamples === 0) {
      return;
    }
    const enough = this.pendingSamples / this.sampleRate >= MERGE_SECONDS;
    if (!enough && !this.ended && this.scheduledAny) {
      return;
    }
    const merged = new Float32Array(this.pendingSamples);
    let offset = 0;
    for (const part of this.pending) {
      merged.set(part, offset);
      offset += part.length;
    }
    this.pending = [];
    this.pendingSamples = 0;
    this.schedule(merged);
  }

  private schedule(samples: Float32Array): void {
    const buffer = this.context.createBuffer(1, samples.length, this.sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);

    const now = this.context.currentTime;
    let when = this.nextStart;
    if (!this.scheduledAny) {
      when = now + START_MARGIN_SECONDS;
      this.onStart?.();
    } else if (when < now) {
      this.underruns += 1;
      when = now + RECOVERY_MARGIN_SECONDS;
    }
    source.onended = () => {
      if (source === this.lastSource) {
        this.lastSourceEnded = true;
        this.finishIfDone();
      }
    };
    source.start(when);
    this.nextStart = when + buffer.duration;
    this.lastSource = source;
    this.lastSourceEnded = false;
    this.scheduledAny = true;
  }

  private finishIfDone(): void {
    if (this.settled || !this.ended || !this.released) {
      return;
    }
    if (this.scheduledAny && !this.lastSourceEnded) {
      return;
    }
    this.settled = true;
    this.settle?.({
      receivedBytes: this.receivedBytes,
      expectedBytes: this.expectedBytes,
      cut: this.aborted || this.expectedBytes === null || this.expectedBytes !== this.receivedBytes,
      underruns: this.underruns,
    });
  }
}
