import type {
  AudioBufferLike,
  AudioContextLike,
  AudioSourceLike,
} from "../speechPlayback";

export class FakeSource implements AudioSourceLike {
  buffer: AudioBufferLike | null = null;
  onended: (() => void) | null = null;
  startedAt: number | null = null;
  connected = false;
  stopped = false;

  connect(): void {
    this.connected = true;
  }

  start(when: number): void {
    this.startedAt = when;
  }

  stop(): void {
    this.stopped = true;
  }

  get endsAt(): number {
    return (this.startedAt ?? 0) + (this.buffer?.duration ?? 0);
  }
}

export class FakeBuffer implements AudioBufferLike {
  readonly length: number;
  readonly sampleRate: number;

  constructor(length: number, sampleRate: number) {
    this.length = length;
    this.sampleRate = sampleRate;
  }

  get duration(): number {
    return this.length / this.sampleRate;
  }

  copyToChannel(): void {}
}

/** Contexto de audio de mentira, com o relogio controlado pelo teste e o fim de cada som simulado. */
export class FakeContext implements AudioContextLike {
  currentTime = 0;
  state: string = "suspended";
  readonly destination = {};
  readonly sources: FakeSource[] = [];
  readonly options: { sampleRate?: number } | undefined;

  constructor(options?: { sampleRate?: number }) {
    this.options = options;
  }

  createBuffer(_channels: number, length: number, sampleRate: number): AudioBufferLike {
    return new FakeBuffer(length, sampleRate);
  }

  createBufferSource(): AudioSourceLike {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }

  resume(): Promise<void> {
    this.state = "running";
    return Promise.resolve();
  }

  close(): Promise<void> {
    this.state = "closed";
    return Promise.resolve();
  }

  advance(seconds: number): void {
    this.currentTime += seconds;
    for (const source of this.sources) {
      if (
        !source.stopped &&
        source.startedAt !== null &&
        source.endsAt <= this.currentTime &&
        source.onended
      ) {
        const done = source.onended;
        source.onended = null;
        done();
      }
    }
  }

  get scheduledSeconds(): number {
    return this.sources.reduce((total, source) => total + (source.buffer?.duration ?? 0), 0);
  }
}
