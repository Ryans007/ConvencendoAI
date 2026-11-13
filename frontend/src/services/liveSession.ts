import { resolveWsBaseUrl } from "../api/origin";
import { AudioPlayer } from "./audioPlayer";
import { AudioRecorder, hasSpeech } from "./audioRecorder";
import { getAccessToken } from "./session";
import { activeSpeechContext, unlockSpeechAudio } from "./speechAudio";
import { SpeechPlayback, type SpeechOutcome } from "./speechPlayback";

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
  errorRetryAfterSeconds: number | null;
  result: LiveSessionResult | null;
  noSpeechNotice: boolean;
  audioTooLargeNotice: boolean;
  studentHasSpoken: boolean;
  speakerName: string | null;
  personaAudible: boolean;
  hint: SessionHint;
}

export const NO_HINT: SessionHint = { status: "idle", text: null };

type Listener = (state: LiveSessionState) => void;

interface ControlMessage {
  type:
    | "session_ended"
    | "error"
    | "no_speech"
    | "audio_too_large"
    | "evaluating"
    | "hint"
    | "hint_unavailable"
    | "speaker"
    | "speech_start"
    | "speech_end";
  attempt_id?: number;
  final_score?: number;
  passed?: boolean;
  message?: string;
  code?: string;
  retry_after_seconds?: number;
  text?: string;
  name?: string;
  sample_rate?: number;
  channels?: number;
  bytes?: number;
}

type QueuedAudio =
  | { kind: "blob"; blob: Blob; speaker: string | null }
  | { kind: "speech"; playback: SpeechPlayback; speaker: string | null };

const DEFAULT_SPEECH_RATE = 24000;

interface PendingOutcome {
  phase: "ended" | "error";
  result?: LiveSessionResult;
  errorMessage?: string;
  errorCode?: string;
  errorRetryAfterSeconds?: number;
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
    errorRetryAfterSeconds: null,
    result: null,
    noSpeechNotice: false,
    audioTooLargeNotice: false,
    studentHasSpoken: false,
    speakerName: null,
    personaAudible: false,
    hint: NO_HINT,
  };

  private readonly audioQueue: QueuedAudio[] = [];
  private announcedSpeaker: string | null = null;
  private playingAudio = false;
  private pendingOutcome: PendingOutcome | null = null;
  private evaluationStarted = false;
  private endedByStudent = false;
  private turnStartedAt: number | null = null;
  private pendingWaitMs: number | null = null;
  private releasedAt: number | null = null;
  private speechContext: AudioContext | null = null;
  private incomingSpeech: SpeechPlayback | null = null;
  private discardingSpeech = false;
  private currentSpeech: SpeechPlayback | null = null;
  private deferredLatencyMs: number | null = null;
  private turnUnderruns = 0;
  private turnCutLines = 0;

  private readonly microphone = new AudioRecorder();
  private readonly player = new AudioPlayer();

  private readonly hintsEnabled: boolean;

  constructor(scenarioSlug: string, levelOrder: number, hintsEnabled = false) {
    const hintsParam = hintsEnabled ? "?hints=1" : "";
    const wsBaseUrl = resolveWsBaseUrl(import.meta.env.VITE_WS_BASE_URL, globalThis.location);
    const url = `${wsBaseUrl}/voice/${scenarioSlug}/${levelOrder}/${hintsParam}`;
    this.hintsEnabled = hintsEnabled;
    this.socket = new WebSocket(url);
    this.socket.binaryType = "arraybuffer";
    this.socket.addEventListener("open", () => {
      this.authenticate();
      this.setState({ phase: "persona-speaking" });
    });
    this.socket.addEventListener("message", (event) => this.handleMessage(event));
    this.socket.addEventListener("close", () => this.handleClose());
  }

  /**
   * Manda o token de acesso na primeira mensagem da conexao, e nunca na URL: o log de acesso do
   * servidor grava a URL inteira, e o token ficaria la. O servidor so inicia a sessao depois
   * desta mensagem e recusa qualquer audio que chegue antes. O token e lido agora, e nao na
   * criacao da sessao, para valer o que a renovacao acabou de emitir. Declara que sabe tocar a fala
   * em fluxo so quando o contexto de audio foi liberado e esta tocando agora, porque a abertura da
   * persona fala antes de qualquer toque na tela da sessao; do contrario o servidor manda a fala
   * inteira, como sempre.
   */
  private authenticate(): void {
    const message: Record<string, unknown> = { type: "auth", token: getAccessToken() ?? "" };
    this.speechContext = activeSpeechContext();
    if (this.speechContext !== null) {
      message.stream_audio = true;
    }
    this.socket.send(JSON.stringify(message));
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
        this.releasedAt = null;
        this.setState({ phase: "student-turn", noSpeechNotice: true });
        return;
      }
      if (payload.type === "audio_too_large") {
        this.releasedAt = null;
        this.setState({ phase: "student-turn", audioTooLargeNotice: true });
        return;
      }
      if (payload.type === "hint") {
        this.setState({ hint: { status: "shown", text: payload.text ?? null } });
        return;
      }
      if (payload.type === "speaker") {
        this.announcedSpeaker = payload.name ?? null;
        if (!this.playingAudio && this.state.phase === "persona-speaking") {
          this.setState({ speakerName: this.announcedSpeaker });
        }
        return;
      }
      if (payload.type === "speech_start") {
        this.startIncomingSpeech(payload);
        return;
      }
      if (payload.type === "speech_end") {
        this.finishIncomingSpeech(payload.bytes ?? 0);
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
          errorRetryAfterSeconds: payload.retry_after_seconds,
        };
      }
      this.settleIfIdle();
      return;
    }

    if (this.incomingSpeech !== null) {
      this.incomingSpeech.push(new Uint8Array(event.data));
      return;
    }
    if (this.discardingSpeech) {
      return;
    }

    this.audioQueue.push({
      kind: "blob",
      blob: new Blob([event.data], { type: "audio/wav" }),
      speaker: this.announcedSpeaker,
    });
    this.announcedSpeaker = null;
    this.playNextAudio();
  }

  /**
   * Toca o proximo audio da fila, um de cada vez. Uma falha de reproducao (bloqueio de
   * autoplay, aba em segundo plano) e registrada no console antes de avancar a fila —
   * sem isso, ela avancava em silencio, como se a fala tivesse sido ouvida.
   *
   * O nome de quem fala vira estado quando o audio dele comeca a tocar, e nao quando chega:
   * numa rodada com duas falas os dois audios chegam juntos, e o nome da segunda so pode
   * aparecer depois que a primeira terminou. `personaAudible` marca que ha uma fala tocando de
   * fato: antes disso a tela diz que a persona esta pensando, e nunca que ela esta falando.
   */
  private playNextAudio(): void {
    if (this.playingAudio || this.audioQueue.length === 0) {
      this.settleIfIdle();
      return;
    }
    this.playingAudio = true;

    const queued = this.audioQueue.shift();
    if (!queued) {
      this.playingAudio = false;
      return;
    }
    if (queued.kind === "speech") {
      this.playQueuedSpeech(queued.playback, queued.speaker);
      return;
    }
    this.setState({ phase: "persona-speaking", speakerName: queued.speaker, personaAudible: true });
    const advance = () => {
      this.playingAudio = false;
      this.playNextAudio();
    };
    this.player.play(queued.blob, () => this.reportTurnLatency()).then(advance, (cause) => {
      console.error("Falha ao reproduzir audio da persona:", cause);
      this.releasedAt = null;
      this.reportPlaybackFailure(cause);
      advance();
    });
  }

  /**
   * Abre uma fala em fluxo: cria o player dela e a poe na fila, no lugar de uma fala inteira. Os
   * pedacos que chegam depois vao para ele ate o aviso de fim. Se o aparelho nao esta preparado
   * (nao ha contexto de audio ativo ou o formato nao e suportado), os pedacos dessa fala sao
   * descartados e o servidor e avisado, e a sessao volta a pedir a fala inteira nas seguintes.
   */
  private startIncomingSpeech(payload: ControlMessage): void {
    this.incomingSpeech = null;
    this.discardingSpeech = false;
    try {
      if (this.speechContext === null) {
        const failure = new Error("sem contexto de audio ativo para a fala em fluxo");
        failure.name = "NoSpeechContext";
        throw failure;
      }
      const playback = new SpeechPlayback(this.speechContext, {
        sampleRate: payload.sample_rate ?? DEFAULT_SPEECH_RATE,
        channels: payload.channels ?? 1,
      });
      this.incomingSpeech = playback;
      this.audioQueue.push({ kind: "speech", playback, speaker: this.announcedSpeaker });
      this.announcedSpeaker = null;
      this.playNextAudio();
    } catch (cause) {
      this.discardingSpeech = true;
      this.speechContext = null;
      this.reportPlaybackFailure(cause);
      if (this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: "stream_audio", enabled: false }));
      }
    }
  }

  /** O servidor terminou a fala em fluxo e disse quantos bytes mandou. */
  private finishIncomingSpeech(bytes: number): void {
    this.incomingSpeech?.finish(bytes);
    this.incomingSpeech = null;
    this.discardingSpeech = false;
  }

  /**
   * Toca a fala em fluxo que e a da vez. O nome de quem fala aparece ja, como "pensando", e a fala so
   * conta como tocando quando o primeiro som comeca, que e tambem o instante da latencia da vez.
   */
  private playQueuedSpeech(playback: SpeechPlayback, speaker: string | null): void {
    this.currentSpeech = playback;
    this.setState({ phase: "persona-speaking", speakerName: speaker, personaAudible: false });
    void playback
      .play(() => {
        this.setState({ personaAudible: true });
        this.reportTurnLatency(true);
      })
      .then((outcome) => {
        this.noteSpeechOutcome(outcome);
        this.currentSpeech = null;
        this.playingAudio = false;
        this.playNextAudio();
      });
  }

  /**
   * Guarda o que a fala em fluxo contou durante a reproducao, para ir na latencia da vez, e avisa o
   * servidor quando ela chegou cortada, porque o console do celular nao e acessivel a quem mantem o
   * sistema.
   */
  private noteSpeechOutcome(outcome: SpeechOutcome): void {
    this.turnUnderruns += outcome.underruns;
    if (!outcome.cut) {
      return;
    }
    this.turnCutLines += 1;
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "speech_cut",
          expected_bytes: outcome.expectedBytes,
          received_bytes: outcome.receivedBytes,
        }),
      );
    }
  }

  /**
   * Manda a latencia que a fala em fluxo deixou guardada, junto do que ela contou. So sai quando a
   * fila esvazia, porque os esvaziamentos e os cortes so se conhecem depois que as falas da vez
   * terminam de tocar.
   */
  private flushDeferredLatency(): void {
    if (this.deferredLatencyMs === null) {
      return;
    }
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "turn_latency",
          total_ms: this.deferredLatencyMs,
          underruns: this.turnUnderruns,
          cut_lines: this.turnCutLines,
        }),
      );
    }
    this.deferredLatencyMs = null;
    this.turnUnderruns = 0;
    this.turnCutLines = 0;
  }

  /**
   * Avisa o servidor de que o navegador recusou tocar uma fala, so com o nome do erro. O console
   * do celular nao e acessivel a quem mantem o sistema, entao o log do servidor e o unico lugar
   * onde a recusa pode ser vista.
   */
  private reportPlaybackFailure(cause: unknown): void {
    const reason = cause instanceof Error ? cause.name : "unknown";
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "playback_failed", reason }));
    }
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
    this.flushDeferredLatency();

    if (this.pendingOutcome) {
      const outcome = this.pendingOutcome;
      this.pendingOutcome = null;
      if (outcome.phase === "ended") {
        this.setState({
          phase: "ended",
          result: outcome.result ?? null,
          speakerName: null,
          personaAudible: false,
        });
      } else {
        this.setState({
          phase: "error",
          speakerName: null,
          personaAudible: false,
          errorMessage: outcome.errorMessage ?? null,
          errorCode: outcome.errorCode ?? null,
          errorRetryAfterSeconds: outcome.errorRetryAfterSeconds ?? null,
        });
      }
      return;
    }

    if (this.evaluationStarted) {
      if (this.state.phase !== "evaluating") {
        this.setState({ phase: "evaluating", speakerName: null, personaAudible: false });
      }
      return;
    }

    if (this.state.phase === "persona-speaking") {
      this.turnStartedAt = Date.now();
      this.setState({
        phase: "student-turn",
        turnCount: this.state.turnCount + 1,
        speakerName: null,
        personaAudible: false,
      });
    }
  }

  /**
   * Conexao fechada sem desfecho conhecido vira "conexao perdida". O servidor fecha logo
   * depois de mandar o fim de sessao; se o ultimo audio ainda estiver tocando, o desfecho
   * esta pendente, e o fechamento nao pode ser tratado como queda.
   */
  private handleClose(): void {
    this.incomingSpeech?.abort();
    this.incomingSpeech = null;
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

  /**
   * Comeca a gravar a fala do aluno. A espera da vez e medida aqui, no toque, e nao quando o
   * microfone termina de abrir: abrir o microfone leva um tempo que nao e do aluno. A espera e
   * contada desde o fim da fala do personagem, entao uma nova gravacao depois de "nao ouvimos"
   * continua contando do mesmo ponto.
   */
  async startRecording(): Promise<void> {
    if (!this.playingAudio) {
      this.player.unlock();
      unlockSpeechAudio();
    }
    if (this.state.phase !== "student-turn" || this.microphone.active) {
      return;
    }
    this.pendingWaitMs = this.turnStartedAt === null ? null : Date.now() - this.turnStartedAt;
    const started = await this.microphone.start();
    if (!started) {
      this.setState({ noSpeechNotice: true });
      return;
    }
    this.setState({ phase: "recording", noSpeechNotice: false, audioTooLargeNotice: false });
  }

  stopRecording(): void {
    if (this.state.phase === "recording") {
      this.releasedAt = Date.now();
    }
    void this.sendRecording();
  }

  /**
   * Informa ao servidor quanto o aluno esperou entre soltar o botao e a fala da persona comecar a
   * tocar. So o navegador sabe os dois instantes, e o servidor junta o total as parcelas dele numa
   * linha de log. Vale uma vez por vez: a segunda fala da mesma rodada nao reporta de novo.
   */
  private reportTurnLatency(streamed = false): void {
    if (this.releasedAt === null) {
      return;
    }
    const totalMs = Date.now() - this.releasedAt;
    this.releasedAt = null;
    if (streamed) {
      this.deferredLatencyMs = totalMs;
      return;
    }
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "turn_latency", total_ms: totalMs }));
    }
  }

  private async sendRecording(): Promise<void> {
    const recording = await this.microphone.stop();
    if (!recording) {
      this.releasedAt = null;
      return;
    }
    if (!hasSpeech(recording)) {
      this.releasedAt = null;
      this.setState({ phase: "student-turn", noSpeechNotice: true });
      return;
    }
    const buffer = await recording.blob.arrayBuffer();
    this.turnUnderruns = 0;
    this.turnCutLines = 0;
    this.sendTurnTiming();
    this.socket.send(buffer);
    this.setState({
      phase: "persona-speaking",
      hint: NO_HINT,
      studentHasSpoken: true,
      speakerName: null,
      personaAudible: false,
    });
  }

  /**
   * Informa ao servidor, logo antes do audio, quanto o aluno esperou para comecar a falar. O
   * servidor usa o tempo so como medida de fluencia; a tela nunca mostra cronometro.
   */
  private sendTurnTiming(): void {
    if (this.pendingWaitMs === null) {
      return;
    }
    this.socket.send(JSON.stringify({ type: "turn_timing", waited_ms: this.pendingWaitMs }));
    this.pendingWaitMs = null;
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

  /**
   * O aluno pede o relatorio antes do limite de turnos: o servidor avalia a conversa ate ali e
   * responde como responde ao fim por limite. So vale na vez do aluno e depois de ele ter falado
   * ao menos uma vez, porque o servidor ignora o pedido antes disso e a tela ficaria esperando um
   * relatorio que nao vem.
   */
  endAndReport(): void {
    if (this.state.phase !== "student-turn" || !this.state.studentHasSpoken) {
      return;
    }
    this.evaluationStarted = true;
    this.socket.send(JSON.stringify({ type: "end_session" }));
    this.setState({ phase: "evaluating" });
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
    for (const queued of this.audioQueue.splice(0)) {
      if (queued.kind === "speech") {
        queued.playback.stop();
      }
    }
    this.incomingSpeech?.stop();
    this.incomingSpeech = null;
    this.currentSpeech?.stop();
    this.microphone.release();
    if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
      this.socket.close();
    }
  }
}
