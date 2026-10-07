import type { CastMember, LevelState, ScenarioState } from "../../api/journey";
import { formatCooldown } from "./scenarioAction";

export type ScenarioMark = "locked" | "passed" | "attempted" | "available";

export type LevelDash = "approved" | "attempted" | "untried";

export interface LevelStatus {
  label: "Aprovado" | "Não atingiu a nota" | "Disponível";
  action: "Começar" | "Refazer";
  cooldown: string | null;
}

/**
 * Estado que a marca da linha do tempo mostra: bloqueado, aprovado, tentou e não passou, ou
 * disponível. A ordem dos testes importa, porque um cenário aprovado também tem tentativas.
 */
export function scenarioMark(scenario: ScenarioState): ScenarioMark {
  if (!scenario.unlocked) {
    return "locked";
  }
  if (scenario.completed) {
    return "passed";
  }
  if (scenario.level_states.some((level) => level.last_attempt !== null)) {
    return "attempted";
  }
  return "available";
}

/** Nível que o cartão abre selecionado: o primeiro ainda não aprovado, ou o último. */
export function initialLevelOrder(scenario: ScenarioState): number {
  const firstPending = scenario.level_states.find((level) => !level.approved);
  return (firstPending ?? scenario.level_states.at(-1))?.order ?? 1;
}

/** Como o tracinho de um nível é pintado: aprovado, tentado sem aprovação, ou nunca tentado. */
export function levelDash(level: LevelState): LevelDash {
  if (level.approved) {
    return "approved";
  }
  return level.last_attempt !== null ? "attempted" : "untried";
}

/** Estado, ação e tempo de espera do nível selecionado, como a coluna do cartão os mostra. */
export function levelStatus(level: LevelState): LevelStatus {
  const tried = level.last_attempt !== null;
  return {
    label: level.approved ? "Aprovado" : tried ? "Não atingiu a nota" : "Disponível",
    action: tried ? "Refazer" : "Começar",
    cooldown:
      level.cooldown_remaining_seconds !== null ? formatCooldown(level.cooldown_remaining_seconds) : null,
  };
}

/** Elenco numa linha só: "Rachel (recrutadora de RH) · Tom (tech lead)". */
export function castLine(cast: CastMember[]): string {
  return cast.map((member) => `${member.name} (${member.scene_function})`).join(" · ");
}
