import type { ClipListItem } from "./types";

/** The design's five shot-size display buckets, same vocabulary as
 * ui/server/coverage_matrix.py's SHOT_COLUMNS — reused for the reel
 * screen's filter checkboxes rather than re-deriving the 8-value enum
 * mapping a third time (DESIGN_IMPLEMENTATION_PLAN.md's notes for
 * Prompt 6). */
export const SHOT_TYPE_BUCKETS = ["WIDE", "MED", "MCU", "CU", "INSERT"] as const;
export type ShotTypeBucket = (typeof SHOT_TYPE_BUCKETS)[number];

/** Toggles `value` in the repeated `key` params of a URLSearchParams,
 * returning a new instance — the filter checkboxes are additive and
 * mirrored into the URL (react-router-dom's useSearchParams), not
 * component state, per Prompt 6's first real use of URL-mirrored filters. */
export function toggleParam(params: URLSearchParams, key: string, value: string): URLSearchParams {
  const next = new URLSearchParams(params);
  const current = next.getAll(key);
  next.delete(key);
  const updated = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  for (const v of updated) next.append(key, v);
  return next;
}

export interface ReelCount {
  reel: string;
  count: number;
}

/** Real per-reel clip counts for the rail's REELS section, derived from
 * the actual clip list rather than a hardcoded list — the mockup's
 * A002/A003/A004 doesn't match this index (only A002 and A007 are real). */
export function reelCounts(clips: ClipListItem[]): ReelCount[] {
  const counts = new Map<string, number>();
  for (const c of clips) counts.set(c.reel, (counts.get(c.reel) ?? 0) + 1);
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([reel, count]) => ({ reel, count }));
}
