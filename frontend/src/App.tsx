import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { RequireAuth } from "./components/RequireAuth";
import CenarioPage from "./pages/cenario/CenarioPage";
import DiagnosticoPage from "./pages/diagnostico/DiagnosticoPage";
import EntradaPage from "./pages/entrada/EntradaPage";
import JornadaPage from "./pages/jornada/JornadaPage";
import RelatorioPage from "./pages/relatorio/RelatorioPage";
import RevisaoPage from "./pages/revisao/RevisaoPage";
import RodadaPage from "./pages/revisao/RodadaPage";
import DefinirSenhaPage from "./pages/senha/DefinirSenhaPage";
import SessaoAoVivoPage from "./pages/sessao/SessaoAoVivoPage";

/** Raiz do app: roteamento entre as telas do fluxo do aluno. */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/entrada" element={<EntradaPage />} />
        <Route path="/definir-senha" element={<DefinirSenhaPage />} />
        <Route path="/diagnostico" element={<DiagnosticoPage />} />

        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="/jornada" element={<JornadaPage />} />
            <Route path="/cenario/:scenarioSlug/:levelOrder" element={<CenarioPage />} />
            <Route path="/relatorio/:attemptId" element={<RelatorioPage />} />
            <Route path="/revisao" element={<RevisaoPage />} />
            <Route path="/revisao/rodada" element={<RodadaPage />} />
          </Route>
          <Route path="/sessao/:scenarioSlug/:levelOrder" element={<SessaoAoVivoPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/jornada" replace />} />
        <Route path="*" element={<Navigate to="/jornada" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
