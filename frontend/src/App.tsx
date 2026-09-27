import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth";
import CenarioPage from "./pages/cenario/CenarioPage";
import DiagnosticoPage from "./pages/diagnostico/DiagnosticoPage";
import EntradaPage from "./pages/entrada/EntradaPage";
import JornadaPage from "./pages/jornada/JornadaPage";
import RelatorioPage from "./pages/relatorio/RelatorioPage";
import SessaoAoVivoPage from "./pages/sessao/SessaoAoVivoPage";

/** Raiz do app: roteamento entre as telas do fluxo do aluno. */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/entrada" element={<EntradaPage />} />
        <Route path="/diagnostico" element={<DiagnosticoPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/jornada" element={<JornadaPage />} />
          <Route path="/cenario/:scenarioSlug/:levelOrder" element={<CenarioPage />} />
          <Route path="/sessao/:scenarioSlug/:levelOrder" element={<SessaoAoVivoPage />} />
          <Route path="/relatorio/:attemptId" element={<RelatorioPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/jornada" replace />} />
        <Route path="*" element={<Navigate to="/jornada" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
