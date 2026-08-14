import { describe, expect, it } from "vitest";
import { rowLabel, statusHoverText } from "./coverageMatrix";
import type { CoverageMatrixRow } from "./types";

function row(overrides: Partial<CoverageMatrixRow> = {}): CoverageMatrixRow {
  return {
    scene: "S01",
    slate: "1A",
    take: 1,
    location: "Amsterdam canal bridge",
    day_night: "DAY",
    description: "Amsterdam canal bridge, Day — 2 chars",
    cells: { WIDE: [], MED: ["01_1a_take"], MCU: [], CU: [], INSERT: [] },
    unknown_clip_ids: [],
    no_visuals_clip_ids: [],
    has_tight_coverage: false,
    status: "NO TIGHT COVERAGE",
    classification: "coverage gap",
    ...overrides,
  };
}

describe("rowLabel", () => {
  it("formats scene · slate from real fields", () => {
    expect(rowLabel(row({ scene: "S03", slate: "2C" }))).toBe("S03 · 2C");
  });
});

describe("statusHoverText", () => {
  it("summarizes which columns actually have takes", () => {
    const text = statusHoverText(row(), "SELECT * FROM clips");
    expect(text).toContain("MED 1");
    expect(text).toContain("no tight");
  });

  it("reports a row with no populated columns honestly", () => {
    const text = statusHoverText(
      row({ cells: { WIDE: [], MED: [], MCU: [], CU: [], INSERT: [] } }),
      "SELECT 1"
    );
    expect(text).toContain("no shots at any mapped size");
  });

  it("notes tight coverage when the row has one", () => {
    const text = statusHoverText(
      row({ cells: { WIDE: [], MED: [], MCU: ["03_2c_take"], CU: [], INSERT: [] }, has_tight_coverage: true }),
      "SELECT 1"
    );
    expect(text).toContain("includes a tight");
  });

  it("includes the real SQL that produced the grid", () => {
    const text = statusHoverText(row(), "SELECT clip_id FROM clips");
    expect(text).toContain("SELECT clip_id FROM clips");
  });
});
