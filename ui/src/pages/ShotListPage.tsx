import { useEffect, useState } from "react";
import { getShotListRows, setShotListRowSelected } from "../api";
import { formatForClipboard, selectedCount, shotListHeadline } from "../shotList";
import { Shell } from "../shell/Shell";
import type { ShotListRow } from "../types";

function Row({ row, onToggle }: { row: ShotListRow; onToggle: (rowId: string, selected: boolean) => void }) {
  return (
    <div className="shot-list-row">
      <button
        type="button"
        role="checkbox"
        aria-checked={row.selected}
        aria-label={`Select ${row.title}`}
        className={row.selected ? "shot-list-row__checkbox shot-list-row__checkbox--checked" : "shot-list-row__checkbox"}
        onClick={() => onToggle(row.row_id, !row.selected)}
      >
        {row.selected && "✓"}
      </button>
      <div className="shot-list-row__body">
        <div className="shot-list-row__heading">
          <span className="shot-list-row__title mono">{row.title}</span>
          <span className="shot-list-row__qualifier mono">{row.qualifier}</span>
        </div>
        <div className="shot-list-row__reason">{row.reason}</div>
        <div className="shot-list-row__pills">
          <span className="shot-list-row__pill mono">
            {row.source_clip ? `from ${row.source_clip}` : "no source clip"}
          </span>
          <span className="shot-list-row__pill shot-list-row__pill--accent mono">{row.classification}</span>
        </div>
      </div>
    </div>
  );
}

export function ShotListPage() {
  const [rows, setRows] = useState<ShotListRow[] | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getShotListRows().then((r) => {
      if (!cancelled) setRows(r);
    });
    // Scopes a print stylesheet to this page only (see index.css) — Shell's
    // top bar and this page's own action buttons live outside the print
    // area, but aren't inside a single printable subtree Shell exposes.
    document.body.classList.add("shot-list-print-target");
    return () => {
      cancelled = true;
      document.body.classList.remove("shot-list-print-target");
    };
  }, []);

  function toggle(rowId: string, selected: boolean) {
    setRows((prev) => prev?.map((r) => (r.row_id === rowId ? { ...r, selected } : r)) ?? prev);
    setShotListRowSelected(rowId, selected).then((updated) => {
      if (!updated) {
        setRows((prev) => prev?.map((r) => (r.row_id === rowId ? { ...r, selected: !selected } : r)) ?? prev);
      }
    });
  }

  function copyForAD() {
    if (!rows || rows.length === 0) return;
    navigator.clipboard?.writeText(formatForClipboard(rows)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const count = rows ? selectedCount(rows) : 0;

  return (
    <Shell
      showRail={false}
      topBarRight={
        <div className="shot-list-page__actions">
          <button type="button" className="shot-list-page__btn" onClick={() => window.print()}>
            Print
          </button>
          <button
            type="button"
            className="shot-list-page__btn shot-list-page__btn--primary"
            onClick={copyForAD}
            disabled={!rows || rows.length === 0}
          >
            {copied ? "Copied" : "Copy for AD"}
          </button>
        </div>
      }
    >
      <div className="shot-list-page">
        <div className="shot-list-panel">
          <div className="shot-list-panel__header">
            <div className="shot-list-panel__overline mono">PICKUPS · FROM TODAY'S GAPS</div>
            <h1 className="shot-list-panel__headline">{shotListHeadline(rows?.length ?? 0)}</h1>
            <p className="shot-list-panel__explainer">
              Each row came out of a real aggregate over today's coverage — a live read of
              ClickHouse's <span className="mono">visuals</span> table — not from anyone's memory.
            </p>
          </div>

          {rows == null && <p className="shot-list-panel__status">Loading…</p>}

          {rows && rows.length === 0 && (
            <p className="shot-list-panel__status">
              No coverage gaps are flagged right now — every scene has tight coverage.
            </p>
          )}

          {rows && rows.length > 0 && (
            <div className="shot-list-rows">
              {rows.map((row) => (
                <Row key={row.row_id} row={row} onToggle={toggle} />
              ))}
            </div>
          )}

          <div className="shot-list-panel__footer">
            <span className="shot-list-panel__footer-count mono">{count} SELECTED</span>
          </div>
        </div>
      </div>
    </Shell>
  );
}
