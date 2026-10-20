import type { LiveSessionPhase } from "../../services/liveSession";

export type EndActionState = "hidden" | "disabled" | "available";

const PHASES_WITH_END_ACTION: LiveSessionPhase[] = ["persona-speaking", "student-turn", "recording"];

/**
 * O estado da acao "Encerrar e ver relatorio". Antes da primeira resposta do aluno ela nao
 * aparece, porque o servidor ignora o pedido e a tela ficaria esperando um relatorio. Depois, ela
 * so vale na vez do aluno, sem gravacao em andamento; enquanto a persona fala ou o aluno grava,
 * fica visivel e desabilitada.
 */
export function endActionState(phase: LiveSessionPhase, studentHasSpoken: boolean): EndActionState {
  if (!studentHasSpoken || !PHASES_WITH_END_ACTION.includes(phase)) {
    return "hidden";
  }
  return phase === "student-turn" ? "available" : "disabled";
}
