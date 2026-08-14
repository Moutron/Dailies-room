import type { ReactNode } from "react";
import { TopBar } from "./TopBar";
import { LeftRail } from "./LeftRail";
import type { SessionTurn } from "../types";

interface ShellProps {
  /** Right-side top bar slot: varies per screen (status readout, buttons, search). */
  topBarRight?: ReactNode;
  /** false for screens with no rail (e.g. clip detail, shot list panel). */
  showRail?: boolean;
  /** Real turns from the current /ask conversation — see LeftRail. */
  sessionTurns?: SessionTurn[];
  /** Screen #1d's real filter checkboxes — see LeftRail. */
  filters?: ReactNode;
  children: ReactNode;
}

export function Shell({ topBarRight, showRail = true, sessionTurns, filters, children }: ShellProps) {
  return (
    <div className="shell">
      <TopBar rightSlot={topBarRight} />
      <div className={showRail ? "shell__body" : "shell__body shell__body--no-rail"}>
        {showRail && <LeftRail sessionTurns={sessionTurns} filters={filters} />}
        <div className="shell__content">{children}</div>
      </div>
    </div>
  );
}
