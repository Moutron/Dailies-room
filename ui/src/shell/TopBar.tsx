import type { ReactNode } from "react";
import { PLACEHOLDER_CHROME } from "./chrome";

interface TopBarProps {
  /** Right-side slot: status readout, buttons, or a search field — varies per screen. */
  rightSlot?: ReactNode;
}

export function TopBar({ rightSlot }: TopBarProps) {
  const crumbs = PLACEHOLDER_CHROME.breadcrumb;
  return (
    <header className="top-bar">
      <div className="top-bar__brand">
        <span className="top-bar__logo" aria-hidden="true">
          DR
        </span>
        <span className="top-bar__name">The Dailies Room</span>
      </div>
      <span className="top-bar__divider" aria-hidden="true" />
      <nav className="top-bar__breadcrumb mono" aria-label="Context">
        {crumbs.map((crumb, i) => (
          <span
            key={crumb}
            className={i === 0 ? "top-bar__crumb top-bar__crumb--active" : "top-bar__crumb"}
          >
            {crumb}
          </span>
        )).reduce<ReactNode[]>((acc, node, i) => {
          if (i > 0) {
            acc.push(
              <span key={`sep-${i}`} className="top-bar__crumb-sep" aria-hidden="true">
                /
              </span>,
            );
          }
          acc.push(node);
          return acc;
        }, [])}
      </nav>
      <div className="top-bar__right">{rightSlot}</div>
      <div className="top-bar__avatar mono" title={PLACEHOLDER_CHROME.userName}>
        {PLACEHOLDER_CHROME.userInitials}
      </div>
    </header>
  );
}
