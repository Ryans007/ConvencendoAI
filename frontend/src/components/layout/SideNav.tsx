import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { useCurrentUser } from "../../hooks/useCurrentUser";
import { useJourney } from "../../hooks/useJourney";
import { useReviewSummary } from "../../hooks/useReviewSummary";
import { activeTrack } from "../../pages/jornada/activeTrack";
import { LogoutLink } from "../LogoutLink";
import { Logo } from "../Logo";
import { activeNavItem, type NavItemId } from "./activeNavItem";

interface SideNavProps {
  id: string;
  open: boolean;
  onClose: () => void;
}

interface NavEntryProps {
  to: string;
  item: NavItemId;
  current: NavItemId | null;
  label: string;
  icon: ReactNode;
  badge?: number;
}

function NavEntry({ to, item, current, label, icon, badge }: NavEntryProps) {
  const isCurrent = current === item;

  return (
    <Link
      to={to}
      aria-current={isCurrent ? "page" : undefined}
      className={`flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-score ${
        isCurrent
          ? "bg-brand-soft font-semibold text-brand-strong"
          : "font-medium text-ink/80 hover:bg-app hover:text-ink"
      }`}
    >
      {icon}
      <span className="flex-1">{label}</span>
      {badge !== undefined && badge > 0 && (
        <>
          <span
            aria-hidden="true"
            className="flex h-[22px] min-w-[22px] items-center justify-center rounded-pill bg-brand-strong px-[7px] text-[12px] font-bold text-white"
          >
            {badge}
          </span>
          <span className="sr-only">{badge === 1 ? "1 item vencido" : `${badge} itens vencidos`}</span>
        </>
      )}
    </Link>
  );
}

const JOURNEY_ICON = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <circle cx="5" cy="4" r="2" />
    <circle cx="13" cy="14" r="2" />
    <path d="M5 6v2.5a3 3 0 0 0 3 3h3" />
  </svg>
);

const REVIEW_ICON = (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3.5 9a5.5 5.5 0 1 0 1.6-3.9" />
    <path d="M3.5 2.8v3h3" />
  </svg>
);

/**
 * Menu lateral das telas logadas: marca, itens de navegação, nome de usuário com o papel na trilha e saída da conta.
 *
 * No celular ele é uma gaveta: fechada, fica fora da tela e invisível, para o foco do teclado
 * não entrar num menu que ninguém vê. Em telas largas, `lg:` o devolve à coluna fixa.
 */
export function SideNav({ id, open, onClose }: SideNavProps) {
  const { pathname } = useLocation();
  const current = activeNavItem(pathname);
  const { data: tracks } = useJourney();
  const { data: review } = useReviewSummary();
  const { data: user } = useCurrentUser();
  const role = activeTrack(tracks)?.student_role;

  return (
    <aside
      id={id}
      aria-label="Menu principal"
      className={`fixed inset-y-0 left-0 z-30 flex w-[280px] flex-col border-r border-line bg-surface px-3.5 pb-4 pt-5 shadow-[0_12px_40px_rgb(23_24_26/0.16)] transition-[transform,visibility] duration-200 ease-out lg:sticky lg:top-0 lg:z-auto lg:h-screen lg:w-[248px] lg:flex-none lg:translate-x-0 lg:shadow-none lg:visible ${
        open ? "visible translate-x-0" : "invisible -translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between gap-2 px-2.5 pb-7 pt-1">
        <div className="flex items-center gap-2.5">
          <Logo size={26} />
          <span className="text-scenario font-semibold tracking-tight">ConvencendoAI</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fechar menu"
          className="flex h-8 w-8 items-center justify-center rounded-pill text-[18px] leading-none text-ink-muted hover:bg-app hover:text-ink lg:hidden"
        >
          &times;
        </button>
      </div>

      <nav aria-label="Navegação" className="flex flex-col gap-0.5">
        <NavEntry to="/jornada" item="journey" current={current} label="Jornada" icon={JOURNEY_ICON} />
        <NavEntry
          to="/revisao"
          item="review"
          current={current}
          label="Revisão"
          icon={REVIEW_ICON}
          badge={review?.due}
        />
      </nav>

      <div className="flex-1" />

      <div className="flex flex-col gap-3.5 border-t border-line px-2.5 pt-4">
        {(user || role) && (
          <div className="flex min-w-0 flex-col gap-0.5 px-0.5">
            {user && (
              <span className="truncate text-score font-semibold leading-snug text-ink">
                {user.username}
              </span>
            )}
            {role && <span className="text-[12px] leading-snug text-ink-muted">{role}</span>}
          </div>
        )}
        <LogoutLink className="w-fit text-aux font-medium text-ink-muted hover:text-ink" />
      </div>
    </aside>
  );
}
