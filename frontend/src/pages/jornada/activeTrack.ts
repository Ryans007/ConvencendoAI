import type { TrackState } from "../../api/journey";

/**
 * Trilha em andamento do aluno: a primeira liberada e ainda não concluída. Se todas estão
 * concluídas, vale a primeira. Sem trilhas carregadas, não há trilha ativa.
 */
export function activeTrack(tracks: TrackState[] | undefined): TrackState | undefined {
  return tracks?.find((track) => track.unlocked && !track.completed) ?? tracks?.[0];
}
