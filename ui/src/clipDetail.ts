import type { DialogueLine } from "./types";

/** Position + width for a dialogue region block on the waveform track,
 * from the line's real start_s/end_s against the clip's real duration_s —
 * never a fixed mockup percentage. Clamped so a line that runs past the
 * clip's measured duration (shouldn't happen post-Prompt-4A, but the UI
 * must not render off the track if it does) never overflows visually. */
export function regionStyle(line: DialogueLine, durationS: number): { left: string; width: string } {
  if (!durationS || durationS <= 0) return { left: "0%", width: "0%" };
  const leftFraction = Math.max(0, Math.min(1, line.start_s / durationS));
  const widthFraction = Math.max(0, Math.min(1 - leftFraction, (line.end_s - line.start_s) / durationS));
  return { left: `${leftFraction * 100}%`, width: `${widthFraction * 100}%` };
}

/** Which transcript line the playhead is currently inside, or -1 for none
 * — drives the promoted violet treatment. A line is "current" for
 * [start_s, end_s), so the boundary moment belongs to the next line. */
export function activeLineIndex(lines: DialogueLine[], currentTimeS: number): number {
  return lines.findIndex((line) => currentTimeS >= line.start_s && currentTimeS < line.end_s);
}

/** The transcript's real, derivable "timing note" pill — how long the line
 * runs, computed from its own start_s/end_s. Never the mockup's invented
 * performance beat ("held pause 0.8s"), which isn't data this pipeline has. */
export function lineDurationLabel(line: DialogueLine): string {
  return `${(line.end_s - line.start_s).toFixed(1)}s line`;
}

/** "2026-08-14 12:30:27" (ClickHouse DateTime string) -> "2026-08-14 · 12:30" */
export function formatIngestedAt(ingestedAt: string): string {
  const [date, time] = ingestedAt.split(/[ T]/);
  if (!date || !time) return ingestedAt;
  return `${date} · ${time.slice(0, 5)}`;
}
