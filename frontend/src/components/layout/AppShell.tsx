import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Logo } from "../Logo";
import { SideNav } from "./SideNav";

const NAV_ID = "main-nav";

/**
 * Moldura das telas logadas: o menu lateral ao lado do conteúdo da rota, que entra pelo
 * `Outlet`. Como é uma rota de layout, o menu continua montado quando o aluno troca de tela.
 *
 * A gaveta do celular guarda em qual caminho foi aberta, em vez de um booleano: ela está
 * aberta só enquanto o caminho atual é o mesmo, então navegar a fecha sem precisar de efeito.
 */
export function AppShell() {
  const { pathname } = useLocation();
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  const drawerOpen = drawerPath === pathname;

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDrawerPath(null);
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  return (
    <div className="flex min-h-screen bg-app">
      {drawerOpen && (
        <button
          type="button"
          aria-label="Fechar menu"
          tabIndex={-1}
          onClick={() => setDrawerPath(null)}
          className="fixed inset-0 z-20 bg-ink/25 lg:hidden"
        />
      )}

      <SideNav id={NAV_ID} open={drawerOpen} onClose={() => setDrawerPath(null)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-3 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerPath(pathname)}
            aria-label="Abrir menu"
            aria-expanded={drawerOpen}
            aria-controls={NAV_ID}
            className="flex h-11 w-11 items-center justify-center rounded-pill text-ink hover:bg-app"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
              <path d="M3 6h14" />
              <path d="M3 10h14" />
              <path d="M3 14h14" />
            </svg>
          </button>
          <Logo size={22} />
          <span className="text-scenario font-semibold tracking-tight">ConvencendoAI</span>
        </div>

        <div className="flex-1">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
