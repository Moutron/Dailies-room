import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CoveragePage } from "./CoveragePage";
import { getClipList, getCoverageMatrix } from "../api";
import type { ClipListItem, CoverageMatrix } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getCoverageMatrix: vi.fn(),
    getClipList: vi.fn(),
  };
});

const mockGetCoverageMatrix = vi.mocked(getCoverageMatrix);
const mockGetClipList = vi.mocked(getClipList);

const MATRIX: CoverageMatrix = {
  columns: ["WIDE", "MED", "MCU", "CU", "INSERT"],
  rows: [
    {
      scene: "S01",
      slate: "1A",
      take: 1,
      location: "Amsterdam canal bridge",
      day_night: "DAY",
      description: "Amsterdam canal bridge, Day — 2 chars",
      cells: { WIDE: [], MED: ["01_1a_take", "01_1b_take", "01_1c_take"], MCU: [], CU: [], INSERT: [] },
      unknown_clip_ids: [],
      no_visuals_clip_ids: [],
      has_tight_coverage: false,
      status: "NO TIGHT COVERAGE",
      classification: "coverage gap",
    },
    {
      scene: "S03",
      slate: "2C",
      take: 3,
      location: "Rooftop lookout, Amsterdam",
      day_night: "NIGHT",
      description: "Rooftop lookout, Amsterdam, Night — 1 char — no dialogue",
      cells: { WIDE: [], MED: [], MCU: ["03_2c_take"], CU: [], INSERT: [] },
      unknown_clip_ids: [],
      no_visuals_clip_ids: [],
      has_tight_coverage: true,
      status: "COMPLETE",
      classification: null,
    },
  ],
  stats: { takes_printed: 6, scenes: 2, gaps_flagged: 1 },
  gap_scenes: ["S01"],
  headline: "Scene S01 is missing tight coverage.",
  sql: "SELECT c.clip_id AS clip_id FROM DailiesRoom.clips AS c",
};

const CLIPS: ClipListItem[] = [
  { clip_id: "01_1a_take", reel: "A002", scene: "S01", slate: "1A", take: 1, duration_s: 4.8, shot_type: "medium", circled: true },
  { clip_id: "01_1b_take", reel: "A002", scene: "S01", slate: "1A", take: 1, duration_s: 5.5, shot_type: "medium", circled: false },
  { clip_id: "03_2c_take", reel: "A007", scene: "S03", slate: "2C", take: 3, duration_s: 2.1, shot_type: "medium_close", circled: false },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <CoveragePage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockGetCoverageMatrix.mockReset();
  mockGetClipList.mockReset().mockResolvedValue(CLIPS);
});

describe("CoveragePage", () => {
  it("renders real cells from the coverage matrix endpoint", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    renderPage();

    await waitFor(() => expect(screen.getByText("Scene S01 is missing tight coverage.")).toBeInTheDocument());
    expect(screen.getByText("01_1a_take")).toBeInTheDocument();
    expect(screen.getByText("01_1b_take")).toBeInTheDocument();
    expect(screen.getByText("03_2c_take")).toBeInTheDocument();
  });

  it("renders hatched gap cells for empty columns, not fabricated chips", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    // S01/1A has takes only in MED: 4 gap cells (WIDE, MCU, CU, INSERT).
    // S03/2C has a take only in MCU: 4 gap cells (WIDE, MED, CU, INSERT).
    expect(container.querySelectorAll(".coverage-matrix__gap-cell")).toHaveLength(8);
  });

  it("take chips link to the real clip detail route", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    const link = screen.getByText("01_1a_take").closest("a");
    expect(link).toHaveAttribute("href", "/clip/01_1a_take");
  });

  it("renders the real takes-printed / scenes / gaps-flagged stats", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    renderPage();

    await waitFor(() => expect(screen.getByText("Scene S01 is missing tight coverage.")).toBeInTheDocument());
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("legend names the real table and column, not the mockup's clips_meta.shot_size", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    renderPage();

    await waitFor(() => expect(screen.getByText("visuals.shot_type")).toBeInTheDocument());
    expect(screen.queryByText(/clips_meta/)).not.toBeInTheDocument();
    expect(screen.queryByText(/shot_size/)).not.toBeInTheDocument();
  });

  it("send-gaps-to-shot-list is a real link to the shot list, not a disabled stub", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    renderPage();

    await waitFor(() => expect(screen.getByText("Send gaps to shot list")).toBeInTheDocument());
    const link = screen.getByText("Send gaps to shot list");
    expect(link).toHaveAttribute("href", "/shot-list");
  });

  it("only a flagged row's gap cells link to the shot list", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    // S01/1A is flagged (classification: coverage gap) -> its 4 gap cells link out.
    // S03/2C is COMPLETE (classification: null) -> its 4 gap cells are inert.
    expect(container.querySelectorAll(".coverage-matrix__gap-cell--flagged")).toHaveLength(4);
    expect(container.querySelectorAll(".coverage-matrix__gap-cell--flagged")).toHaveLength(
      container.querySelectorAll("a.coverage-matrix__gap-cell").length
    );
  });

  it("stars only the real circled take chip", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    expect(container.querySelectorAll(".coverage-matrix__chip--circled")).toHaveLength(1);
    expect(screen.getByText("★")).toBeInTheDocument();
  });

  it("status label hover reveals the real SQL", async () => {
    mockGetCoverageMatrix.mockResolvedValue(MATRIX);

    renderPage();

    await waitFor(() => expect(screen.getByText("NO TIGHT COVERAGE")).toBeInTheDocument());
    expect(screen.getByText("NO TIGHT COVERAGE")).toHaveAttribute(
      "title",
      expect.stringContaining("DailiesRoom.clips")
    );
  });
});
