import { AudioRecorder, MIN_RECORDING_MS } from "./audioRecorder";
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

export type SessionHintStatus = "idle" | "loading" | "shown" | "unavailable";

export interface SessionHint {
  status: SessionHintStatus;
  text: string | null;
}

export interface LiveSessionState {
  phase: LiveSessionPhase;
  turnCount: number;
  errorMessage: string | null;
  errorCode: string | null;
  result: LiveSessionResult | null;
  noSpeechNotice: boolean;
  audioTooLargeNotice: boolean;
  hint: SessionHint;
}

export const NO_HINT: SessionHint = { status: "idle", text: null };

type Listener = (state: LiveSessionState) => void;

interface ControlMessage {
  type: "session_ended" | "error" | "no_speech" | "audio_too_large" | "evaluating" | "hint" | "hint_unavailable";
  attempt_id?: number;
  final_score?: number;
  passed?: boolean;
  message?: string;
  code?: string;
  text?: string;
}

interface PendingOutcome {
  phase: "ended" | "error";
  result?: LiveSessionResult;
  errorMessage?: string;
  errorCode?: string;
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
    errorCode: null,
    result: null,
    noSpeechNotice: false,
    audioTooLargeNotice: false,
    hint: NO_HINT,
  };

  private readonly audioQueue: Blob[] = [];
  private playingAudio = false;
  private pendingOutcome: PendingOutcome | null = null;
  private evaluationStarted = false;
  private endedByStudent = false;

  private readonly microphone = new AudioRecorder();

  private readonly hintsEnabled: boolean;

  constructor(scenarioSlug: string, levelOrder: number, hintsEnabled = false) {
    const token = getAccessToken() ?? "";
    const hintsParam = hintsEnabled ? "&hints=1" : "";
    const url = `${wsBaseUrl}/voice/${scenarioSlug}/${levelOrder}/?token=${encodeURIComponent(token)}${hintsParam}`;
    this.hintsEnabled = hintsEnabled;
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
      if (payload.type === "audio_too_large") {
        this.setState({ phase: "student-turn", audioTooLargeNotice: true });
        return;
      }
      if (payload.type === "hint") {
        this.setState({ hint: { status: "shown", text: payload.text ?? null } });
        return;
      }
      if (payload.type === "hint_unavailable") {
        this.setState({ hint: { status: "unavailable", text: null } });
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
        this.pendingOutcome = {
          phase: "error",
          errorMessage: payload.message ?? "Falha na sessao.",
          errorCode: payload.code,
        };
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
        this.setState({
          phase: "error",
          errorMessage: outcome.errorMessage ?? null,
          errorCode: outcome.errorCode ?? null,
        });
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

  /**
   * Conexao fechada sem desfecho conhecido vira "conexao perdida". O servidor fecha logo
   * depois de mandar o fim de sessao; se o ultimo audio ainda estiver tocando, o desfecho
   * esta pendente, e o fechamento nao pode ser tratado como queda.
   */
  private handleClose(): void {
    if (
      this.endedByStudent ||
      this.pendingOutcome !== null ||
      this.state.phase === "ended" ||
      this.state.phase === "error"
    ) {
      return;
    }
    this.setState({ phase: "connection-lost" });
  }

  async startRecording(): Promise<void> {
    if (this.state.phase !== "student-turn" || this.microphone.active) {
      return;
    }
    const started = await this.microphone.start();
    if (!started) {
      this.setState({ noSpeechNotice: true });
      return;
    }
    this.setState({ phase: "recording", noSpeechNotice: false, audioTooLargeNotice: false });
  }

  stopRecording(): void {
    void this.sendRecording();
  }

  private async sendRecording(): Promise<void> {
    const recording = await this.microphone.stop();
    if (!recording) {
      return;
    }
    if (recording.durationMs < MIN_RECORDING_MS) {
      this.setState({ phase: "student-turn", noSpeechNotice: true });
      return;
    }
    const buffer = await recording.blob.arrayBuffer();
    this.socket.send(buffer);
    this.setState({ phase: "persona-speaking", hint: NO_HINT });
  }

  /**
   * Pede ao servidor a dica da vez atual. So vale numa sessao aberta com as dicas ligadas,
   * na vez do aluno, e uma vez por vez: com a dica ja pedida ou visivel, nada e enviado
   * de novo. A dica volta a "idle" quando o aluno envia a resposta.
   */
  requestHint(): void {
    if (!this.hintsEnabled || this.state.phase !== "student-turn") {
      return;
    }
    if (this.state.hint.status === "loading" || this.state.hint.status === "shown") {
      return;
    }
    this.setState({ hint: { status: "loading", text: null } });
    this.socket.send(JSON.stringify({ type: "hint_request" }));
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
    this.microphone.release();
    if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
      this.socket.close();
    }
  }
}
