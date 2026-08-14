import { describe, expect, it } from "vitest";
import { activeLineIndex, formatIngestedAt, lineDurationLabel, regionStyle } from "./clipDetail";
import type { DialogueLine } from "./types";

function line(overrides: Partial<DialogueLine>): DialogueLine {
  return {
    segment_idx: 0,
    start_s: 0,
    end_s: 1,
    speaker: "MAN",
    text: "hi",
    delivery: "flat",
    ...overrides,
  };
}

describe("regionStyle", () => {
  it("computes left/width fractions from real start_s/end_s against duration_s", () => {
    const style = regionStyle(line({ start_s: 1.375, end_s: 2.75 }), 5.5);
    expect(style.left).toBe("25%");
    expect(style.width).toBe("25%");
  });

  it("clamps a line that runs past the clip duration rather than overflowing", () => {
    const style = regionStyle(line({ start_s: 5.0, end_s: 6.0 }), 5.5);
    expect(style.left).toBe(`${(5.0 / 5.5) * 100}%`);
    expect(parseFloat(style.width)).toBeCloseTo((0.5 / 5.5) * 100, 5);
  });

  it("returns zero-width for a zero or missing duration rather than dividing by zero", () => {
    expect(regionStyle(line({}), 0)).toEqual({ left: "0%", width: "0%" });
  });
});

describe("activeLineIndex", () => {
  const lines = [line({ start_s: 0, end_s: 2 }), line({ start_s: 4, end_s: 4.9 })];

  it("finds the line containing the playhead", () => {
    expect(activeLineIndex(lines, 4.5)).toBe(1);
  });

  it("returns -1 when the playhead is in a gap between lines", () => {
    expect(activeLineIndex(lines, 3.0)).toBe(-1);
  });

  it("treats end_s as exclusive — the boundary belongs to the next line", () => {
    expect(activeLineIndex(lines, 2.0)).toBe(-1);
  });

  it("returns -1 for an empty line list", () => {
    expect(activeLineIndex([], 1.0)).toBe(-1);
  });
});

describe("lineDurationLabel", () => {
  it("derives the label from the line's own start_s/end_s", () => {
    expect(lineDurationLabel(line({ start_s: 0, end_s: 3.8 }))).toBe("3.8s line");
  });
});

describe("formatIngestedAt", () => {
  it("splits date and time, dropping seconds", () => {
    expect(formatIngestedAt("2026-08-14 12:30:27")).toBe("2026-08-14 · 12:30");
  });

  it("handles a T separator too", () => {
    expect(formatIngestedAt("2026-08-14T12:30:27")).toBe("2026-08-14 · 12:30");
  });

  it("returns the raw string unchanged if it doesn't parse", () => {
    expect(formatIngestedAt("not-a-date")).toBe("not-a-date");
  });
});
