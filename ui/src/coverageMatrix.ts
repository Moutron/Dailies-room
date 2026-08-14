import type { CoverageMatrixRow } from "./types";

/** "S01 · 1A" — the row label, mono, matching the mockup's "07 · 1A" shape
 * with a real scene id instead of the invented "07". */
export function rowLabel(row: CoverageMatrixRow): string {
  return `${row.scene} · ${row.slate}`;
}

/** The status label's hover text: a real, mechanical breakdown of which
 * columns this row's own cells populated (never a "trust me" claim), plus
 * the real aggregate SQL that produced the whole grid — the "how did you
 * know that" affordance the design calls for, without inventing a second
 * per-row query. */
export function statusHoverText(row: CoverageMatrixRow, sql: string): string {
  const counts = Object.entries(row.cells)
    .filter(([, clipIds]) => clipIds.length > 0)
    .map(([column, clipIds]) => `${column} ${clipIds.length}`)
    .join(", ");
  const breakdown = counts || "no shots at any mapped size";
  const tight = row.has_tight_coverage ? "includes a tight (MCU/CU) shot" : "no tight (MCU/CU) shot";
  return `${breakdown} — ${tight}.\n\n${sql.trim()}`;
}
