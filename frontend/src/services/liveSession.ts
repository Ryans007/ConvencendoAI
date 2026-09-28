import { getAccessToken } from "./session";

const DEFAULT_WS_BASE_URL = "ws://localhost:8010/ws";
const wsBaseUrl: string = import.meta.env.VITE_WS_BASE_URL ?? DEFAULT_WS_BASE_URL;

export type LiveSessionPhase =
  | "connecting"
  | "persona-speaking"
  | "student-turn"
  | "recording"
  | "evaluating"
  | "ended"
  | "left"
  | "connection-lost"
  | "error";

export interface LiveSessionResult {
  attemptId: number;
  finalScore: number;
  passed: boolean;
}

export interface LiveSessionState {
  phase: LiveSessionPhase;
  turnCount: number;
  errorMessage: string | null;
  result: LiveSessionResult | null;
  noSpeechNotice: boolean;
}

type Listener = (state: LiveSessionState) => void;

interface ControlMessage {
  type: "session_ended" | "error" | "no_speech" | "evaluating";
  attempt_id?: number;
  final_score?: number;
  passed?: boolean;
  message?: string;
}

interface PendingOutcome {
  phase: "ended" | "error";
  result?: LiveSessionResult;
  errorMessage?: string;
}

/**
 * Uma conexao de sessao de voz ao vivo: WebSocket autenticado, captura por push-to-talk
 * e reproducao sequencial do audio das personas. Uma instancia por sessao — descarte ao
 * sair da tela.
 *
 * Fica fora do React de proposito — e o mesmo protocolo que o cliente de teste HTML ja
 * validou (backend/apps/voice/static/voice/test_client.html), so que reaproveitavel por
 * um hook em vez de reescrito a mao em cada tela.
 */
export class LiveSession {
  private readonly socket: WebSocket;
  private readonly listeners = new Set<Listener>();
  private state: LiveSessionState = {
    phase: "connecting",
    turnCount: 0,
    errorMessage: null,
    result: null,
    noSpeechNotice: false,
  };

  private readonly audioQueue: Blob[] = [];
  private playingAudio = false;
  private pendingOutcome: PendingOutcome | null = null;
  private evaluationStarted = false;
  private endedByStudent = false;

  private mediaStream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private recordedChunks: Blob[] = [];

  constructor(scenarioSlug: string, levelOrder: number) {
    const token = getAccessToken() ?? "";
    const url = `${wsBaseUrl}/voice/${scenarioSlug}/${levelOrder}/?token=${encodeURIComponent(token)}`;
    this.socket = new WebSocket(url);
    this.socket.binaryType = "arraybuffer";
    this.socket.addEventListener("open", () => this.setState({ phase: "persona-speaking" }));
    this.socket.addEventListener("message", (event) => this.handleMessage(event));
    this.socket.addEventListener("close", () => this.handleClose());
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private setState(patch: Partial<LiveSessionState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  private handleMessage(event: MessageEvent<string | ArrayBuffer>): void {
    if (typeof event.data === "string") {
      const payload = JSON.parse(event.data) as ControlMessage;
      if (payload.type === "no_speech") {
        this.setState({ phase: "student-turn", noSpeechNotice: true });
        return;
      }
      if (payload.type === "evaluating") {
        this.evaluationStarted = true;
      } else if (payload.type === "session_ended") {
        this.pendingOutcome = {
          phase: "ended",
          result: {
            attemptId: payload.attempt_id ?? 0,
            finalScore: payload.final_score ?? 0,
            passed: payload.passed ?? false,
          },
        };
      } else if (payload.type === "error") {
        this.pendingOutcome = { phase: "error", errorMessage: payload.message ?? "Falha na sessao." };
      }
      this.settleIfIdle();
      return;
    }

    this.audioQueue.push(new Blob([event.data], { type: "audio/wav" }));
    this.playNextAudio();
  }

  /**
   * Toca o proximo audio da fila, um de cada vez. Uma falha de reproducao (bloqueio de
   * autoplay, aba em segundo plano) e registrada no console antes de avancar a fila —
   * sem isso, ela avancava em silencio, como se a fala tivesse sido ouvida.
   */
  private playNextAudio(): void {
    if (this.playingAudio || this.audioQueue.length === 0) {
      this.settleIfIdle();
      return;
    }
    this.playingAudio = true;
    if (this.state.phase !== "persona-speaking") {
      this.setState({ phase: "persona-speaking" });
    }

    const blob = this.audioQueue.shift();
    if (!blob) {
      this.playingAudio = false;
      return;
    }
    const audio = new Audio(URL.createObjectURL(blob));
    const advance = () => {
      this.playingAudio = false;
      this.playNextAudio();
    };
    audio.addEventListener("ended", advance);
    audio.play().catch((cause) => {
      console.error("Falha ao reproduzir audio da persona:", cause);
      advance();
    });
  }

  /**
   * So resolve o desfecho pendente (fim de sessao ou erro) quando o audio ja acabou de tocar.
   *
   * Depois do aviso de avaliacao, a fila vazia leva a fase de avaliacao, e nunca de volta a
   * vez do aluno: a cena ja terminou, e o servidor ignoraria qualquer fala enviada ali.
   */
  private settleIfIdle(): void {
    if (this.playingAudio || this.audioQueue.length > 0) {
      return;
    }

    if (this.pendingOutcome) {
      const outcome = this.pendingOutcome;
      this.pendingOutcome = null;
      if (outcome.phase === "ended") {
        this.setState({ phase: "ended", result: outcome.result ?? null });
      } else {
        this.setState({ phase: "error", errorMessage: outcome.errorMessage ?? null });
      }
      return;
    }

    if (this.evaluationStarted) {
      if (this.state.phase !== "evaluating") {
        this.setState({ phase: "evaluating" });
      }
      return;
    }

    if (this.state.phase === "persona-speaking") {
      this.setState({ phase: "student-turn", turnCount: this.state.turnCount + 1 });
    }
  }

  private handleClose(): void {
    if (this.endedByStudent || this.state.phase === "ended" || this.state.phase === "error") {
      return;
    }
    this.setState({ phase: "connection-lost" });
  }

  async startRecording(): Promise<void> {
    if (this.state.phase !== "student-turn") {
      return;
    }
    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.recordedChunks = [];
    this.recorder = new MediaRecorder(this.mediaStream);
    this.recorder.ondataavailable = (event) => this.recordedChunks.push(event.data);
    this.recorder.onstop = () => this.sendRecording();
    this.recorder.start();
    this.setState({ phase: "recording", noSpeechNotice: false });
  }

  stopRecording(): void {
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }
  }

  private sendRecording(): void {
    const mimeType = this.recorder?.mimeType ?? "audio/webm";
    const blob = new Blob(this.recordedChunks, { type: mimeType });
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;

    blob.arrayBuffer().then((buffer) => {
      this.socket.send(buffer);
      this.setState({ phase: "persona-speaking" });
    });
  }

  /** O aluno decide sair antes do fim: encerra a conexao, sem produzir relatorio. */
  leaveEarly(): void {
    this.endedByStudent = true;
    this.socket.close();
    this.setState({ phase: "left" });
  }

  /** Libera a conexao e o microfone ao desmontar a tela. */
  dispose(): void {
    this.endedByStudent = true;
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
      this.socket.close();
    }
  }
}
