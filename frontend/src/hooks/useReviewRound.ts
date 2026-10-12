import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { ApiError, apiErrorCode } from "../api/client";
import { discardItem, fetchAnswerAudio, sendAnswer, type RoundItem } from "../api/reviewRound";
import { AudioPlayer } from "../services/audioPlayer";
import { AudioRecorder, hasSpeech } from "../services/audioRecorder";
import { INITIAL_ROUND_STATE, roundReducer, type RoundState } from "../services/reviewRound";

const RECORDABLE_PHASES = ["idle", "not_heard", "too_many", "mic_denied"];
const CONFLICT = 409;
const TOO_MANY_REQUESTS_CODE = "too_many_requests";

function startRound(items: RoundItem[]): RoundState {
  return roundReducer(INITIAL_ROUND_STATE, { type: "loaded", items });
}

/**
 * Liga a rodada de revisão ao mundo: grava a fala, envia a resposta, toca a forma correta e
 * descarta itens. As decisões de tela ficam no `roundReducer`; aqui só ficam os efeitos, para
 * o reducer continuar uma função pura testável.
 *
 * Recebe os itens já carregados e nasce com eles: quem carrega a rodada é a tela pai, que
 * recria este hook, com uma `key` nova, a cada rodada. O servidor é a fonte da etapa e da
 * tentativa: depois de cada resposta, o que ele devolve em `next` vira o estado. Um 409 (o item
 * já andou, por exemplo num envio duplicado) pede à tela pai que recarregue a rodada, em vez de
 * tentar adivinhar o estado.
 */
export function useReviewRound(items: RoundItem[], reloadRound: () => void) {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(roundReducer, items, startRound);
  const [microphone] = useState(() => new AudioRecorder());
  const [player] = useState(() => new AudioPlayer());
  const [listening, setListening] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const stateRef = useRef<RoundState>(state);
  const lastRecording = useRef<Blob | null>(null);
  const pressed = useRef(false);
  const started = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  });

  useEffect(() => () => microphone.release(), [microphone]);

  const refreshSummary = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["review-summary"] });
  }, [queryClient]);

  const submit = useCallback(
    async (blob: Blob) => {
      const { items: roundItems, index } = stateRef.current;
      try {
        const response = await sendAnswer(roundItems[index].id, blob);
        dispatch({ type: "answered", response });
      } catch (error) {
        if (error instanceof ApiError && error.status === CONFLICT) {
          reloadRound();
          return;
        }
        if (error instanceof ApiError && apiErrorCode(error) === TOO_MANY_REQUESTS_CODE) {
          dispatch({ type: "tooMany" });
          return;
        }
        dispatch({ type: "failed" });
      }
    },
    [reloadRound],
  );

  const finishRecording = useCallback(async () => {
    started.current = false;
    const recording = await microphone.stop();
    if (!recording || !hasSpeech(recording)) {
      dispatch({ type: "tooShort" });
      return;
    }
    lastRecording.current = recording.blob;
    dispatch({ type: "submitted" });
    await submit(recording.blob);
  }, [microphone, submit]);

  const startRecording = useCallback(async () => {
    if (pressed.current || !RECORDABLE_PHASES.includes(stateRef.current.phase)) {
      return;
    }
    pressed.current = true;
    setActionError(null);
    try {
      await microphone.start();
    } catch {
      pressed.current = false;
      dispatch({ type: "micDenied" });
      return;
    }
    started.current = true;
    dispatch({ type: "recordingStarted" });
    if (!pressed.current) {
      await finishRecording();
    }
  }, [microphone, finishRecording]);

  const stopRecording = useCallback(async () => {
    pressed.current = false;
    if (started.current) {
      await finishRecording();
    }
  }, [finishRecording]);

  const retryAnswer = useCallback(async () => {
    if (!lastRecording.current) {
      return;
    }
    dispatch({ type: "retry" });
    await submit(lastRecording.current);
  }, [submit]);

  const continueRound = useCallback(() => {
    const finishesItem = !stateRef.current.last?.next;
    dispatch({ type: "continue" });
    if (finishesItem) {
      refreshSummary();
    }
  }, [refreshSummary]);

  const confirmDiscard = useCallback(async () => {
    const { items: roundItems, index } = stateRef.current;
    try {
      await discardItem(roundItems[index].id);
    } catch (error) {
      const alreadyGone = error instanceof ApiError && error.status === 404;
      if (!alreadyGone) {
        dispatch({ type: "cancelDiscard" });
        setActionError("Não foi possível descartar o item agora. Tente de novo.");
        return;
      }
    }
    dispatch({ type: "discarded" });
    refreshSummary();
  }, [refreshSummary]);

  const listen = useCallback(async () => {
    const answerId = stateRef.current.last?.answer_id;
    if (!answerId || listening) {
      return;
    }
    player.unlock();
    setListening(true);
    setActionError(null);
    try {
      await player.play(await fetchAnswerAudio(answerId));
    } catch {
      setActionError("Não foi possível tocar o áudio agora.");
    } finally {
      setListening(false);
    }
  }, [listening, player]);

  return {
    state,
    listening,
    actionError,
    startRecording,
    stopRecording,
    retryAnswer,
    continueRound,
    askDiscard: () => dispatch({ type: "askDiscard" }),
    cancelDiscard: () => dispatch({ type: "cancelDiscard" }),
    confirmDiscard,
    listen,
  };
}
