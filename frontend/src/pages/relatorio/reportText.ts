import type { AttemptReport, ReportScoring, SpeechMetrics } from "../../api/attemptReport";
import { DIMENSION_LABELS } from "./dimensionLabels";

const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

function percent(fraction: number): string {
  return `${whole.format(fraction * 100)}%`;
}

/**
 * As medidas de fala que aparecem junto de uma dimensão, em frases curtas para o aluno. Só
 * fluência e vocabulário têm medidas; as que o servidor mandou vazias (porque o nível não as
 * usa ou a sessão não as tem) não aparecem.
 */
export function dimensionMeasures(dimension: string, metrics: SpeechMetrics | null): string[] {
  if (!metrics) {
    return [];
  }
  const lines: string[] = [];
  if (dimension === "fluency") {
    if (metrics.reaction_seconds !== null) {
      lines.push(`Tempo para começar a responder: ${decimal.format(metrics.reaction_seconds)} s`);
    }
    if (metrics.words_per_minute !== null) {
      lines.push(`Velocidade: ${whole.format(metrics.words_per_minute)} palavras por minuto`);
    }
    if (metrics.long_pauses_per_100_words !== null) {
      lines.push(
        `Pausas longas: ${decimal.format(metrics.long_pauses_per_100_words)} a cada 100 palavras`,
      );
    }
  }
  if (dimension === "vocabulary") {
    if (metrics.lexical_diversity !== null) {
      lines.push(`Variedade de palavras: ${percent(metrics.lexical_diversity)}`);
    }
    if (metrics.lexical_range !== null) {
      lines.push(`Palavras menos comuns: ${percent(metrics.lexical_range)}`);
    }
  }
  return lines;
}

/** Uma linha da tabela de pesos: a dimensão, os pontos obtidos e o peso dela na tentativa. */
export interface WeightLine {
  label: string;
  value: number;
  weight: number;
}

/** Tudo o que a seção "Como sua nota é calculada" mostra, já em texto para o aluno. */
export interface ScoringExplanation {
  weights: WeightLine[];
  achieved: number;
  possible: number;
  finalScore: number;
  passingScore: number;
  fluency: string | null;
  vocabulary: string | null;
}

function fluencyText(scoring: ReportScoring): string | null {
  const shares = scoring.fluency;
  if (!shares) {
    return null;
  }
  const parts = [
    { share: shares.reaction_share, label: "tempo para começar a responder" },
    { share: shares.speed_share, label: "velocidade" },
    { share: shares.pauses_share, label: "pausas longas" },
  ].filter((part) => part.share > 0);
  const measured =
    parts.length === 1
      ? parts[0].label
      : parts.map((part) => `${part.label} ${percent(part.share)}`).join(", ");
  return (
    `Fluência: ${percent(shares.measured_share)} vem das medidas da sua fala (${measured}) ` +
    `e ${percent(1 - shares.measured_share)} do avaliador, que olha se a fala ficou clara.`
  );
}

function vocabularyText(scoring: ReportScoring): string | null {
  const shares = scoring.vocabulary;
  if (!shares) {
    return null;
  }
  const parts = [`${percent(shares.judged_share)} do avaliador, que olha a precisão das palavras`];
  if (shares.diversity_share > 0) {
    parts.push(`${percent(shares.diversity_share)} da variedade de palavras`);
  }
  if (shares.range_share > 0) {
    parts.push(`${percent(shares.range_share)} das palavras menos comuns`);
  }
  return `Vocabulário: ${parts.join(", ")}.`;
}

/**
 * Monta a explicação da nota a partir do que o servidor mandou, sem repetir nenhuma fórmula
 * de cálculo na tela: os pesos e as proporções vêm prontos no relatório.
 */
export function scoringExplanation(report: AttemptReport): ScoringExplanation {
  const weights = report.score_breakdowns.map((breakdown) => ({
    label: DIMENSION_LABELS[breakdown.dimension] ?? breakdown.dimension,
    value: breakdown.value,
    weight: breakdown.weight,
  }));
  return {
    weights,
    achieved: weights.reduce((sum, line) => sum + line.value, 0),
    possible: weights.reduce((sum, line) => sum + line.weight, 0),
    finalScore: report.final_score,
    passingScore: report.scoring.passing_score,
    fluency: fluencyText(report.scoring),
    vocabulary: vocabularyText(report.scoring),
  };
}
