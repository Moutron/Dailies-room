import type { ShotListRow } from "./types";

/** Real count of persisted, user-selected rows — the footer's "N SELECTED". */
export function selectedCount(rows: ShotListRow[]): number {
  return rows.filter((r) => r.selected).length;
}

/** A real, count-driven headline — never the mockup's fabricated "Four
 * shots to get before we strike the bridge" (a plot detail nothing in this
 * index knows about). Generic wrap-adjacent phrasing, but the number is
 * always the real row count. */
export function shotListHeadline(rowCount: number): string {
  if (rowCount === 0) return "Nothing flagged — every scene has tight coverage.";
  if (rowCount === 1) return "One shot to get before wrap.";
  return `${rowCount} shots to get before wrap.`;
}

/** "Send to AD" has no integration — this is what actually happens: a
 * formatted plaintext list goes to the clipboard. Only the selected rows
 * if any are selected, otherwise every flagged row, so an unfiltered click
 * still produces something useful. */
export function formatForClipboard(rows: ShotListRow[]): string {
  const chosen = rows.filter((r) => r.selected);
  const toFormat = chosen.length > 0 ? chosen : rows;
  return toFormat
    .map((r) => {
      const source = r.source_clip ? `from ${r.source_clip}` : "no source clip";
      return `${r.title} (${r.qualifier}) — ${r.reason} [${r.classification}, ${source}]`;
    })
    .join("\n");
}
