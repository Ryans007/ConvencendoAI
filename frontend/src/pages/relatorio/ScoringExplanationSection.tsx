import type { AttemptReport } from "../../api/attemptReport";
import { scoringExplanation } from "./reportText";

interface ScoringExplanationSectionProps {
  report: AttemptReport;
}

/**
 * Seção recolhível "Como sua nota é calculada", fechada ao abrir o relatório: os pesos da
 * tentativa, a conta da nota final, por que a pronúncia não entra e, quando houve medidas, como
 * fluência e vocabulário combinam medida e avaliador.
 */
export default function ScoringExplanationSection({ report }: ScoringExplanationSectionProps) {
  const explanation = scoringExplanation(report);

  return (
    <details className="group mb-8 rounded-card border border-line bg-surface p-7 shadow-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-aux font-semibold uppercase tracking-wide text-ink-muted">
        Como sua nota é calculada
        <span aria-hidden="true" className="transition-transform group-open:rotate-180">
          ▾
        </span>
      </summary>

      <div className="mt-5 flex flex-col gap-4 text-[15px] leading-relaxed text-ink/80">
        <p>
          Cada dimensão tem um peso neste cenário e nível. A nota final é a soma dos seus pontos
          dividida pela soma dos pesos avaliados, vezes 100.
        </p>

        <table className="w-full text-left text-aux">
          <thead>
            <tr className="text-ink-muted">
              <th scope="col" className="pb-2 font-medium">Dimensão</th>
              <th scope="col" className="pb-2 text-right font-medium">Pontos</th>
              <th scope="col" className="pb-2 text-right font-medium">Peso</th>
            </tr>
          </thead>
          <tbody>
            {explanation.weights.map((line) => (
              <tr key={line.label} className="border-t border-line">
                <td className="py-1.5">{line.label}</td>
                <td className="py-1.5 text-right">{line.value}</td>
                <td className="py-1.5 text-right">{line.weight}</td>
              </tr>
            ))}
            <tr className="border-t border-line font-semibold text-ink">
              <td className="py-1.5">Total</td>
              <td className="py-1.5 text-right">{explanation.achieved}</td>
              <td className="py-1.5 text-right">{explanation.possible}</td>
            </tr>
          </tbody>
        </table>

        <p>
          {explanation.achieved} ÷ {explanation.possible} × 100 = {explanation.finalScore}. A
          aprovação é a partir de {explanation.passingScore}.
        </p>
        <p>
          A pronúncia ainda não é avaliada, então ela não entra na conta e não tira pontos de
          você.
        </p>
        {explanation.fluency && <p>{explanation.fluency}</p>}
        {explanation.vocabulary && <p>{explanation.vocabulary}</p>}
      </div>
    </details>
  );
}
