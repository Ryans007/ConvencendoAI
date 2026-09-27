import { useEffect, useRef, useState } from "react";

import { LiveSession, type LiveSessionState } from "../services/liveSession";

export interface UseLiveSessionResult extends LiveSessionState {
  startRecording: () => void;
  stopRecording: () => void;
  leaveEarly: () => void;
}

const INITIAL_STATE: LiveSessionState = {
  phase: "connecting",
  turnCount: 0,
  errorMessage: null,
  result: null,
  noSpeechNotice: false,
};

/** Hook que abre e expoe uma sessao de voz ao vivo, uma instancia por montagem da tela. */
export function useLiveSession(scenarioSlug: string, levelOrder: number): UseLiveSessionResult {
  const sessionRef = useRef<LiveSession | null>(null);
  const [state, setState] = useState<LiveSessionState>(INITIAL_STATE);

  useEffect(() => {
    const session = new LiveSession(scenarioSlug, levelOrder);
    sessionRef.current = session;
    const unsubscribe = session.subscribe(setState);

    return () => {
      unsubscribe();
      session.dispose();
      sessionRef.current = null;
    };
  }, [scenarioSlug, levelOrder]);

  return {
    ...state,
    startRecording: () => {
      void sessionRef.current?.startRecording();
    },
    stopRecording: () => sessionRef.current?.stopRecording(),
    leaveEarly: () => sessionRef.current?.leaveEarly(),
  };
}
