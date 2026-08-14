import type { ReactNode } from "react";

interface TopBarProps {
  /** Right-side slot: status readout, buttons, or a search field — varies per screen. */
  rightSlot?: ReactNode;
}

export function TopBar({ rightSlot }: TopBarProps) {
  return (
    <header className="top-bar">
      <div className="top-bar__brand">
        <span className="top-bar__logo" aria-hidden="true">
          DR
        </span>
        <span className="top-bar__name">The Dailies Room</span>
      </div>
      <div className="top-bar__right">{rightSlot}</div>
    </header>
  );
}
