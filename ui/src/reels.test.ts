import { describe, expect, it } from "vitest";
import { reelCounts, toggleParam } from "./reels";
import type { ClipListItem } from "./types";

function clip(overrides: Partial<ClipListItem> = {}): ClipListItem {
  return {
    clip_id: "01_1a_take",
    reel: "A002",
    scene: "S01",
    slate: "1A",
    take: 1,
    duration_s: 4.8,
    shot_type: "medium",
    circled: false,
    ...overrides,
  };
}

describe("toggleParam", () => {
  it("adds a value not already present", () => {
    const params = new URLSearchParams();
    const next = toggleParam(params, "reel", "A002");
    expect(next.getAll("reel")).toEqual(["A002"]);
  });

  it("removes a value already present, additively (leaves siblings alone)", () => {
    const params = new URLSearchParams("reel=A002&reel=A007");
    const next = toggleParam(params, "reel", "A002");
    expect(next.getAll("reel")).toEqual(["A007"]);
  });

  it("does not mutate the params passed in", () => {
    const params = new URLSearchParams("reel=A002");
    toggleParam(params, "reel", "A007");
    expect(params.getAll("reel")).toEqual(["A002"]);
  });

  it("leaves other keys untouched", () => {
    const params = new URLSearchParams("shot_type=WIDE");
    const next = toggleParam(params, "reel", "A002");
    expect(next.getAll("shot_type")).toEqual(["WIDE"]);
    expect(next.getAll("reel")).toEqual(["A002"]);
  });
});

describe("reelCounts", () => {
  it("counts real clips per reel, from the actual list — not a hardcoded reel list", () => {
    const clips = [
      clip({ clip_id: "01_1a_take", reel: "A002" }),
      clip({ clip_id: "01_1b_take", reel: "A002" }),
      clip({ clip_id: "03_2a_take", reel: "A007" }),
    ];

    expect(reelCounts(clips)).toEqual([
      { reel: "A002", count: 2 },
      { reel: "A007", count: 1 },
    ]);
  });

  it("returns an empty list for no clips", () => {
    expect(reelCounts([])).toEqual([]);
  });
});
