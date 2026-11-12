import type { CastMember, LastAttempt, LevelState, ScenarioState } from "../../api/journey";
import { formatCooldown } from "./scenarioAction";

export type ScenarioMark = "locked" | "passed" | "attempted" | "available";

export type LevelDash = "approved" | "attempted" | "untried";

export interface LevelStatus {
  label: "Aprovado" | "Não atingiu a nota" | "Disponível";
  action: "Começar" | "Refazer";
  cooldown: string | null;
}

export interface ScenarioLatestAttempt {
  levelOrder: number;
  attempt: LastAttempt;
}

/**
 * Diz se `candidate` foi concluída depois de `current`, pelo mesmo critério do backend:
 * `completed_at` e, no empate, o `id` maior. As datas são comparadas como instantes, e não
 * como texto, porque chegam em ISO 8601 com fuso e o texto ordena errado entre fusos
 * diferentes. Uma data ilegível não decide nada, e o `id` desempata.
 */
function concludedAfter(candidate: LastAttempt, current: LastAttempt): boolean {
  const difference = Date.parse(candidate.completed_at) - Date.parse(current.completed_at);
  if (difference !== 0 && !Number.isNaN(difference)) {
    return difference > 0;
  }
  return candidate.id > current.id;
}

/**
 * Tentativa concluída mais recente do aluno no cenário, com a ordem do nível em que foi feita,
 * ou `null` se ele nunca concluiu uma. Cada `last_attempt` já é a mais recente do seu nível, e
 * a API não inclui sessões abandonadas, então basta escolher a mais recente entre os níveis.
 */
export function latestAttempt(scenario: ScenarioState): ScenarioLatestAttempt | null {
  let latest: ScenarioLatestAttempt | null = null;
  for (const level of scenario.level_states) {
    const attempt = level.last_attempt;
    if (attempt !== null && (latest === null || concludedAfter(attempt, latest.attempt))) {
      latest = { levelOrder: level.order, attempt };
    }
  }
  return latest;
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

/**
 * Nível que o cartão abre selecionado: o da tentativa concluída mais recente do aluno no
 * cenário, aprovada ou não, para que a nota que abre o último relatório apareça sem clique.
 * Sem tentativa concluída, o primeiro nível ainda não aprovado, ou o último. Na prática essa
 * reserva dá o primeiro nível, porque não há aprovação sem tentativa concluída, mas ela não
 * depende dessa garantia da API.
 */
export function initialLevelOrder(scenario: ScenarioState): number {
  const latest = latestAttempt(scenario);
  if (latest !== null) {
    return latest.levelOrder;
  }
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

/**
 * `key` do cartão do cenário: o slug e a tentativa concluída mais recente. O cartão escolhe o
 * nível inicial só ao montar, e a jornada pode aparecer primeiro com uma cópia antiga do
 * cache, de antes da sessão. Quando a versão atualizada traz uma tentativa nova, a `key` muda,
 * o React remonta o cartão e o nível é escolhido de novo. Sem tentativa nova a `key` é a
 * mesma, e o nível que o aluno escolheu nos tracinhos continua selecionado.
 */
export function scenarioCardKey(scenario: ScenarioState): string {
  const latest = latestAttempt(scenario);
  return `${scenario.slug}:${latest === null ? "none" : latest.attempt.id}`;
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
