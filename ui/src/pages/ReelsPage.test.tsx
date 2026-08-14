import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ReelsPage } from "./ReelsPage";
import { getClipList, getStats, searchClips } from "../api";
import type { ClipListItem, IndexStats, SearchResponse } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getClipList: vi.fn(),
    getStats: vi.fn(),
    searchClips: vi.fn(),
  };
});

const mockGetClipList = vi.mocked(getClipList);
const mockGetStats = vi.mocked(getStats);
const mockSearchClips = vi.mocked(searchClips);

const CLIPS: ClipListItem[] = [
  {
    clip_id: "01_1a_take",
    reel: "A002",
    scene: "S01",
    slate: "1A",
    take: 1,
    duration_s: 4.8,
    shot_type: "medium",
    circled: true,
  },
  {
    clip_id: "01_1b_take",
    reel: "A002",
    scene: "S01",
    slate: "1A",
    take: 1,
    duration_s: 5.5,
    shot_type: "medium",
    circled: false,
  },
  {
    clip_id: "03_2c_take",
    reel: "A007",
    scene: "S03",
    slate: "2C",
    take: 3,
    duration_s: 2.1,
    shot_type: "medium_close",
    circled: false,
  },
];

const STATS: IndexStats = { clip_count: 6, total_duration_s: 29.83 };

function renderPage(initialEntries = ["/reels"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <ReelsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockGetClipList.mockReset().mockResolvedValue(CLIPS);
  mockGetStats.mockReset().mockResolvedValue(STATS);
  mockSearchClips.mockReset();
});

describe("ReelsPage", () => {
  it("renders real contact-sheet tiles from the clip list endpoint", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    expect(screen.getByText("03_2c_take")).toBeInTheDocument();
  });

  it("renders real index stats in the section header", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText(/6 clips/)).toBeInTheDocument());
  });

  it("tiles link to the real clip detail route", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    const link = screen.getByText("01_1a_take").closest("a");
    expect(link).toHaveAttribute("href", "/clip/01_1a_take");
  });

  it("stars only the real circled tile", async () => {
    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    expect(container.querySelectorAll(".reels-tile--circled")).toHaveLength(1);
    expect(screen.getByText("★")).toBeInTheDocument();
  });

  it("the circled-takes-only filter is a real, working filter mirrored into the URL", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("01_1b_take")).toBeInTheDocument());
    const checkbox = screen.getByRole("checkbox", { name: /circled takes only/i });
    expect(checkbox).not.toBeDisabled();

    await user.click(checkbox);

    expect(checkbox).toBeChecked();
    expect(screen.getByText("01_1a_take")).toBeInTheDocument();
    expect(screen.queryByText("01_1b_take")).not.toBeInTheDocument();
  });

  it("loading a circled=1 URL directly reproduces the filtered view", async () => {
    renderPage(["/reels?circled=1"]);

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    expect(screen.queryByText("01_1b_take")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /circled takes only/i })).toBeChecked();
  });

  it("clicking a reel filter checkbox mirrors the selection into the URL", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("A002")).toBeInTheDocument());
    await user.click(screen.getByRole("checkbox", { name: /A002/ }));

    await waitFor(() => expect(mockGetClipList).toHaveBeenCalledWith(["A002"], []));
  });

  it("loading a filtered URL directly reproduces the filtered view", async () => {
    renderPage(["/reels?reel=A007&shot_type=MCU"]);

    await waitFor(() => expect(mockGetClipList).toHaveBeenCalledWith(["A007"], ["MCU"]));
    const reelCheckbox = await screen.findByRole("checkbox", { name: /A007/ });
    expect(reelCheckbox).toBeChecked();
  });

  it("submitting a search shows the mode-toggle-driven query results with a score badge in semantic mode", async () => {
    const semanticResult: SearchResponse = {
      query: "robotic hand",
      mode: "semantic",
      hits: [
        {
          kind: "dialogue",
          clip_id: "01_1b_take",
          scene: "S01",
          take: 1,
          reel: "A002",
          timecode_in: "01:00:11:12",
          quote: "my robot hand",
          speaker: "CELIA",
          note: "defensive",
          note_label: "performance note",
          score: 0.91,
        },
      ],
    };
    mockSearchClips.mockResolvedValue(semanticResult);
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    await user.type(screen.getByLabelText("Search"), "robotic hand");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText("“my robot hand”")).toBeInTheDocument());
    expect(screen.getByText("0.91")).toBeInTheDocument();
    expect(mockSearchClips).toHaveBeenCalledWith("robotic hand", "semantic");
  });

  it("keyword-mode results never show a score badge", async () => {
    const keywordResult: SearchResponse = {
      query: "robot",
      mode: "keyword",
      hits: [
        {
          kind: "dialogue",
          clip_id: "01_1b_take",
          scene: "S01",
          take: 1,
          reel: "A002",
          timecode_in: "01:00:11:12",
          quote: "my robot hand",
          speaker: "CELIA",
          note: "defensive",
          note_label: "performance note",
          score: null,
        },
      ],
    };
    mockSearchClips.mockResolvedValue(keywordResult);
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("01_1a_take")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "SEMANTIC" }));
    await user.type(screen.getByLabelText("Search"), "robot");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText("“my robot hand”")).toBeInTheDocument());
    expect(screen.queryByText("0.91")).not.toBeInTheDocument();
    expect(mockSearchClips).toHaveBeenCalledWith("robot", "keyword");
  });
});
