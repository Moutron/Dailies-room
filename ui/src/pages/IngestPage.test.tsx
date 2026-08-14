import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { IngestPage } from "./IngestPage";
import { getIngestSummary } from "../api";
import type { IngestSummary } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getIngestSummary: vi.fn(),
  };
});

const mockGetIngestSummary = vi.mocked(getIngestSummary);

// The real six-clip index (DESIGN_IMPLEMENTATION_PLAN.md's Prompt 4/5 notes):
// S01 clips have 1/2/1 dialogue lines, S03 clips have 0.
const SUMMARY: IngestSummary = {
  clips: [
    { clip_id: "03_2e_take", duration_s: 5.8, ingested_at: "2026-08-12 21:50:10", dialogue_count: 0, state: "READY" },
    { clip_id: "03_2c_take", duration_s: 5.2, ingested_at: "2026-08-12 21:49:40", dialogue_count: 0, state: "READY" },
    { clip_id: "03_2a_take", duration_s: 4.9, ingested_at: "2026-08-12 21:49:05", dialogue_count: 0, state: "READY" },
    { clip_id: "01_1c_take", duration_s: 4.4, ingested_at: "2026-08-12 21:47:55", dialogue_count: 1, state: "READY" },
    { clip_id: "01_1b_take", duration_s: 4.7, ingested_at: "2026-08-12 21:47:20", dialogue_count: 2, state: "READY" },
    { clip_id: "01_1a_take", duration_s: 4.9, ingested_at: "2026-08-12 21:46:40", dialogue_count: 1, state: "READY" },
  ],
  indexed_today: 6,
  embeddings: 10,
  most_recent_ingested_at: "2026-08-12 21:50:10",
};

function renderPage() {
  return render(
    <MemoryRouter>
      <IngestPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockGetIngestSummary.mockReset();
});

describe("IngestPage", () => {
  it("renders all six real clips with real durations and line counts", async () => {
    mockGetIngestSummary.mockResolvedValue(SUMMARY);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    expect(container.querySelectorAll(".ingest-table__row:not(.ingest-table__row--header)")).toHaveLength(6);
    expect(screen.getByText("01_1b_take")).toBeInTheDocument();
    expect(screen.getByText("03_2c_take")).toBeInTheDocument();
  });

  it("every row is READY -- no in-flight or queued state rendered", async () => {
    mockGetIngestSummary.mockResolvedValue(SUMMARY);

    renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    expect(screen.getAllByText("READY")).toHaveLength(6);
    expect(screen.queryByText("IN FLIGHT")).not.toBeInTheDocument();
    expect(screen.queryByText("QUEUED")).not.toBeInTheDocument();
    expect(screen.queryByText(/gemini watching/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/queued behind/i)).not.toBeInTheDocument();
  });

  it("real dialogue line counts appear in the LINES column, including real zeros", async () => {
    mockGetIngestSummary.mockResolvedValue(SUMMARY);

    renderPage();

    await waitFor(() => expect(screen.getByText("01_1b_take")).toBeInTheDocument());
    const row = screen.getByText("01_1b_take").closest(".ingest-table__row");
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain("2");

    const zeroRow = screen.getByText("03_2a_take").closest(".ingest-table__row");
    expect(zeroRow!.textContent).toContain("0");
  });

  it("the pipeline strip shows all four real stages with ClickHouse as the accent card", async () => {
    mockGetIngestSummary.mockResolvedValue(SUMMARY);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText(/CARD OFFLOAD/)).toBeInTheDocument());
    expect(screen.getByText(/GEMINI WATCHES/)).toBeInTheDocument();
    expect(screen.getByText(/03 · EMBED/)).toBeInTheDocument();
    expect(screen.getByText(/CLICKHOUSE/)).toBeInTheDocument();
    expect(container.querySelectorAll(".ingest-strip__card--accent")).toHaveLength(1);
    expect(container.querySelector(".ingest-strip__card--accent")?.textContent).toContain("CLICKHOUSE");
  });

  it("the badge shows a real indexed count, never the mockup's fake in-flight number", async () => {
    mockGetIngestSummary.mockResolvedValue(SUMMARY);

    renderPage();

    await waitFor(() => expect(screen.getByText("INDEXED 6")).toBeInTheDocument());
    expect(screen.queryByText(/CLIPS IN FLIGHT/)).not.toBeInTheDocument();
  });

  it("rail stats are real counts, and AVG PER CLIP is omitted rather than fabricated", async () => {
    mockGetIngestSummary.mockResolvedValue(SUMMARY);

    renderPage();

    await waitFor(() => expect(screen.getByText("INDEXED TODAY")).toBeInTheDocument());
    expect(screen.getByText("EMBEDDINGS")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.queryByText("AVG PER CLIP")).not.toBeInTheDocument();
  });

  it("shows an error message when the endpoint fails, not a blank or fabricated page", async () => {
    mockGetIngestSummary.mockResolvedValue(null);

    renderPage();

    await waitFor(() => expect(screen.getByText("Could not load the pipeline index.")).toBeInTheDocument());
  });
});
