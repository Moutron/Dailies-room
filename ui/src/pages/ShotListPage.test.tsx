import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ShotListPage } from "./ShotListPage";
import { getShotListRows, setShotListRowSelected } from "../api";
import type { ShotListRow } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getShotListRows: vi.fn(),
    setShotListRowSelected: vi.fn(),
  };
});

const mockGetShotListRows = vi.mocked(getShotListRows);
const mockSetShotListRowSelected = vi.mocked(setShotListRowSelected);

const ROWS: ShotListRow[] = [
  {
    row_id: "S01-1A",
    title: "S01 · 1A",
    qualifier: "amsterdam canal bridge, day",
    reason: "Nothing tighter than MED exists across the 3 takes for this slate.",
    source_clip: "01_1a_take",
    classification: "coverage gap",
    selected: false,
  },
  {
    row_id: "S03-2A",
    title: "S03 · 2A",
    qualifier: "rooftop lookout, amsterdam, night",
    reason: "Only wide coverage exists for this slate — no medium or tighter take was shot.",
    source_clip: "03_2a_take",
    classification: "wide coverage only",
    selected: true,
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <ShotListPage />
    </MemoryRouter>
  );
}

let mockWriteText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGetShotListRows.mockReset().mockResolvedValue(ROWS);
  mockSetShotListRowSelected.mockReset();
  mockWriteText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: mockWriteText },
    configurable: true,
  });
  document.body.className = "";
});

describe("ShotListPage", () => {
  it("renders real rows generated from the coverage aggregate", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("S01 · 1A")).toBeInTheDocument());
    expect(screen.getByText("S03 · 2A")).toBeInTheDocument();
    expect(screen.getByText(/Nothing tighter than MED/)).toBeInTheDocument();
  });

  it("provenance pills name the real source clip and classification", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("from 01_1a_take")).toBeInTheDocument());
    expect(screen.getByText("coverage gap")).toBeInTheDocument();
    expect(screen.getByText("wide coverage only")).toBeInTheDocument();
  });

  it("shows an honest empty state when nothing is flagged", async () => {
    mockGetShotListRows.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText(/every scene has tight coverage/)).toBeInTheDocument();
  });

  it("the real headline names the actual flagged-row count", async () => {
    renderPage();

    expect(await screen.findByText("2 shots to get before wrap.")).toBeInTheDocument();
  });

  it("footer count reflects the real persisted selection", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("1 SELECTED")).toBeInTheDocument());
  });

  it("toggling a checkbox writes the real selection", async () => {
    mockSetShotListRowSelected.mockResolvedValue({ ...ROWS[0], selected: true });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("S01 · 1A")).toBeInTheDocument());
    await user.click(screen.getByRole("checkbox", { name: /select s01 · 1a/i }));

    expect(mockSetShotListRowSelected).toHaveBeenCalledWith("S01-1A", true);
    await waitFor(() => expect(screen.getByText("2 SELECTED")).toBeInTheDocument());
  });

  it("reverts the optimistic toggle if the write fails", async () => {
    mockSetShotListRowSelected.mockResolvedValue(null);
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("S01 · 1A")).toBeInTheDocument());
    await user.click(screen.getByRole("checkbox", { name: /select s01 · 1a/i }));

    await waitFor(() => expect(screen.getByText("1 SELECTED")).toBeInTheDocument());
  });

  it("Print calls the real window.print, not a fake success state", async () => {
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => {});
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("S01 · 1A")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Print" }));

    expect(printSpy).toHaveBeenCalled();
    printSpy.mockRestore();
  });

  it("Copy for AD copies a real formatted list to the clipboard, honestly labeled", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("S01 · 1A")).toBeInTheDocument());
    expect(screen.queryByText("Send to AD")).not.toBeInTheDocument();

    const btn = screen.getByRole("button", { name: "Copy for AD" });
    fireEvent.click(btn);

    await waitFor(() => expect(mockWriteText).toHaveBeenCalledWith(expect.stringContaining("S03 · 2A")));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});
