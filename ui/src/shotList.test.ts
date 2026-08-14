import { describe, expect, it } from "vitest";
import { formatForClipboard, selectedCount, shotListHeadline } from "./shotList";
import type { ShotListRow } from "./types";

function row(overrides: Partial<ShotListRow> = {}): ShotListRow {
  return {
    row_id: "S01-1A",
    title: "S01 · 1A",
    qualifier: "amsterdam canal bridge, day",
    reason: "Nothing tighter than MED exists across the 3 takes for this slate.",
    source_clip: "01_1a_take",
    classification: "coverage gap",
    selected: false,
    ...overrides,
  };
}

describe("selectedCount", () => {
  it("counts only the real, persisted selected rows", () => {
    const rows = [row({ selected: true }), row({ row_id: "S03-2A", selected: false })];
    expect(selectedCount(rows)).toBe(1);
  });

  it("is zero when nothing is selected", () => {
    expect(selectedCount([row(), row({ row_id: "S03-2A" })])).toBe(0);
  });
});

describe("shotListHeadline", () => {
  it("is honest about zero flagged rows, never the mockup's fabricated plot detail", () => {
    expect(shotListHeadline(0)).toContain("Nothing flagged");
  });

  it("uses singular phrasing for exactly one row", () => {
    expect(shotListHeadline(1)).toBe("One shot to get before wrap.");
  });

  it("uses the real count for more than one row", () => {
    expect(shotListHeadline(3)).toBe("3 shots to get before wrap.");
  });
});

describe("formatForClipboard", () => {
  it("formats only the selected rows when any are selected", () => {
    const rows = [row({ selected: true }), row({ row_id: "S03-2A", title: "S03 · 2A", selected: false })];
    const text = formatForClipboard(rows);
    expect(text).toContain("S01 · 1A");
    expect(text).not.toContain("S03 · 2A");
  });

  it("falls back to every row when none are selected", () => {
    const rows = [row(), row({ row_id: "S03-2A", title: "S03 · 2A" })];
    const text = formatForClipboard(rows);
    expect(text).toContain("S01 · 1A");
    expect(text).toContain("S03 · 2A");
  });

  it("includes the real reason, classification, and source clip", () => {
    const text = formatForClipboard([row()]);
    expect(text).toContain("Nothing tighter than MED");
    expect(text).toContain("coverage gap");
    expect(text).toContain("from 01_1a_take");
  });

  it("honestly names a row with no real source clip", () => {
    const text = formatForClipboard([row({ source_clip: "" })]);
    expect(text).toContain("no source clip");
  });
});
