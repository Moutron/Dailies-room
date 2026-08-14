import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { SessionTurn } from "../types";

interface NavItem {
  to: string;
  label: string;
  badge?: string;
  liveDot?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/ask", label: "Ask" },
  { to: "/coverage", label: "Coverage" },
  { to: "/reels", label: "Reels" },
  { to: "/shot-list", label: "Shot list", badge: "4" },
  { to: "/ingest", label: "Ingest", liveDot: true },
];

interface LeftRailProps {
  /** Real turns from the current /ask conversation, most recent last —
   * replaces the section with "THIS SESSION" when present. Undefined (not
   * an empty array) on every other screen, since there's no session there. */
  sessionTurns?: SessionTurn[];
  /** Extra rail content below the workspace nav — Screen #1d's real filter
   * checkboxes, for the one screen that needs them. Undefined everywhere
   * else. */
  filters?: ReactNode;
}

export function LeftRail({ sessionTurns, filters }: LeftRailProps) {
  return (
    <nav className="left-rail" aria-label="Sections">
      <div className="left-rail__label mono">WORKSPACE</div>
      <ul className="left-rail__list">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                isActive ? "left-rail__item left-rail__item--active" : "left-rail__item"
              }
            >
              <span className="left-rail__active-bar" aria-hidden="true" />
              <span className="left-rail__item-label">{item.label}</span>
              {item.badge && <span className="left-rail__badge mono">{item.badge}</span>}
              {item.liveDot && <span className="left-rail__live-dot" aria-hidden="true" />}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="left-rail__divider" role="presentation" />
      {filters}

      {sessionTurns && sessionTurns.length > 0 && (
        <>
          <div className="left-rail__label mono">THIS SESSION</div>
          <ul className="left-rail__session-list">
            {sessionTurns.map((turn) => (
              <li
                key={turn.id}
                className={turn.active ? "left-rail__session-turn left-rail__session-turn--active" : "left-rail__session-turn"}
              >
                {turn.text}
              </li>
            ))}
          </ul>
          <div className="left-rail__grounding">
            <div className="left-rail__grounding-label mono">GROUNDING</div>
            <p className="left-rail__grounding-body">
              Answers come only from indexed clips. Nothing is inferred from the script.
            </p>
          </div>
        </>
      )}
    </nav>
  );
}
