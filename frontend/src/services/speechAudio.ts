import { createSilence } from "./audioPlayer";

const SPEECH_SAMPLE_RATE = 24000;

type AudioContextConstructor = new (options?: AudioContextOptions) => AudioContext;

let context: AudioContext | null = null;
let silence: HTMLAudioElement | null = null;

function contextConstructor(): AudioContextConstructor | null {
  const scope = globalThis as unknown as {
    AudioContext?: AudioContextConstructor;
    webkitAudioContext?: AudioContextConstructor;
  };
  return scope.AudioContext ?? scope.webkitAudioContext ?? null;
}

/**
 * Libera o audio das falas em fluxo. Deve ser chamado de forma sincrona dentro do tratador de um
 * toque do aluno: o contexto de audio so toca depois de ser retomado por um gesto, e a abertura da
 * persona toca antes de qualquer toque na tela da sessao, entao o gesto certo e o do botao que a
 * inicia. Cria o contexto uma vez, na taxa do audio da fala para o navegador nao reamostrar cada
 * pedaco, e o reaproveita em todas as falas; chamar de novo so o retoma. Toca tambem um instante de
 * silencio num elemento de audio, que no iPhone faz o som sair mesmo com a chavinha de silencioso.
 * Nunca falha: um aparelho que recusa so fica sem fala em fluxo.
 */
export function unlockSpeechAudio(): void {
  const Constructor = contextConstructor();
  if (Constructor === null) {
    return;
  }
  try {
    if (context === null || context.state === "closed") {
      try {
        context = new Constructor({ sampleRate: SPEECH_SAMPLE_RATE });
      } catch {
        context = new Constructor();
      }
    }
    void context.resume().catch(() => undefined);
    if (silence === null && typeof Audio !== "undefined") {
      silence = new Audio();
      silence.src = URL.createObjectURL(createSilence());
    }
    void silence?.play().catch(() => undefined);
  } catch {
    context = null;
  }
}

/** O contexto de audio das falas, mas so se ele estiver tocando agora; do contrario, `null`. */
export function activeSpeechContext(): AudioContext | null {
  return context !== null && context.state === "running" ? context : null;
}

/** Fecha o contexto de audio das falas, por exemplo ao sair da conta. */
export function releaseSpeechAudio(): void {
  void context?.close().catch(() => undefined);
  context = null;
  silence = null;
}
