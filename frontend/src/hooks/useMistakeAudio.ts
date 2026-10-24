import { useCallback, useState } from "react";

import { fetchMistakeAudio } from "../api/attemptReport";
import { AudioPlayer } from "../services/audioPlayer";

/**
 * Toca a forma correta de um erro do relatório. Um áudio por vez: enquanto um toca, os botões
 * "Ouvir" ficam parados, e `playingId` diz qual erro está tocando. O player é liberado dentro
 * do toque do aluno, como na revisão, para o navegador do celular aceitar tocar depois da
 * espera pela rede.
 */
export function useMistakeAudio(attemptId: number) {
  const [player] = useState(() => new AudioPlayer());
  const [playingId, setPlayingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const listen = useCallback(
    async (mistakeId: number) => {
      if (playingId !== null) {
        return;
      }
      player.unlock();
      setPlayingId(mistakeId);
      setError(null);
      try {
        await player.play(await fetchMistakeAudio(attemptId, mistakeId));
      } catch {
        setError("Não foi possível tocar o áudio agora.");
      } finally {
        setPlayingId(null);
      }
    },
    [attemptId, playingId, player],
  );

  return { playingId, error, listen };
}
