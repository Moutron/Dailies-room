import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ClipDetailPage } from "./ClipDetailPage";
import { getClipDialogue, getClipMeta, getClipUrl, setCircled } from "../api";
import type { ClipMeta, DialogueLine } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getClipUrl: vi.fn(),
    getClipMeta: vi.fn(),
    getClipDialogue: vi.fn(),
    setCircled: vi.fn(),
  };
});

const mockGetClipUrl = vi.mocked(getClipUrl);
const mockGetClipMeta = vi.mocked(getClipMeta);
const mockGetClipDialogue = vi.mocked(getClipDialogue);
const mockSetCircled = vi.mocked(setCircled);

const META: ClipMeta = {
  clip_id: "01_1b_take",
  scene: "S01",
  slate: "1A",
  take: 1,
  location: "Amsterdam canal bridge",
  day_night: "DAY",
  duration_s: 6.0,
  reel: "A002",
  ingested_at: "2026-08-14 12:30:27",
  tc_start_s: 0,
  shot_type: "medium",
  camera_movement: "static",
  description: "Two people talk on a bridge.",
  notable_elements: ["bridge"],
  dialogue_count: 2,
  circled: false,
};

const LINES: DialogueLine[] = [
  {
    segment_idx: 0,
    start_s: 0.0,
    end_s: 3.8,
    speaker: "ROBOT_ARM_WOMAN",
    text: "Why don't you just admit that you're freaked out by my robot hand?",
    delivery: "accusatory, frustrated",
  },
  {
    segment_idx: 1,
    start_s: 4.0,
    end_s: 4.9,
    speaker: "MAN",
    text: "I'm not freaked out by, but it's...",
    delivery: "defensive",
  },
];

function renderAt(clipId: string) {
  return render(
    <MemoryRouter initialEntries={[`/clip/${clipId}`]}>
      <Routes>
        <Route path="/clip/:clipId" element={<ClipDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockGetClipUrl.mockReset();
  mockGetClipMeta.mockReset();
  mockGetClipDialogue.mockReset();
  mockSetCircled.mockReset();
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
});

describe("ClipDetailPage", () => {
  it("renders dialogue regions positioned from real start_s/end_s against duration_s", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);

    const { container } = renderAt("01_1b_take");

    await waitFor(() => expect(container.querySelectorAll(".clip-detail__region")).toHaveLength(2));
    const regions = container.querySelectorAll<HTMLElement>(".clip-detail__region");
    expect(regions[0].style.left).toBe("0%");
    expect(regions[0].style.width).toBe(`${(3.8 / 6.0) * 100}%`);
    expect(regions[1].style.left).toBe(`${(4.0 / 6.0) * 100}%`);
  });

  it("clicking a dialogue region seeks the player", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);

    const { container } = renderAt("01_1b_take");
    await waitFor(() => expect(container.querySelectorAll(".clip-detail__region")).toHaveLength(2));

    const video = container.querySelector("video")!;
    const secondRegion = container.querySelectorAll<HTMLElement>(".clip-detail__region")[1];
    fireEvent.click(secondRegion);

    expect(video.currentTime).toBe(4.0);
  });

  it("clicking a transcript line seeks the player to its start_s", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);

    renderAt("01_1b_take");
    const line = await screen.findByText("I'm not freaked out by, but it's...");
    const container2 = line.closest("button")!;
    fireEvent.click(container2);

    const video = document.querySelector("video")!;
    expect(video.currentTime).toBe(4.0);
  });

  it("promotes the transcript line matching the playhead", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);

    const { container } = renderAt("01_1b_take");
    const video = await waitFor(() => {
      const v = container.querySelector("video");
      if (!v) throw new Error("no video yet");
      return v;
    });

    Object.defineProperty(video, "currentTime", { writable: true, value: 4.5 });
    fireEvent.timeUpdate(video);

    await waitFor(() => {
      const active = container.querySelector(".clip-detail__line--active");
      expect(active?.textContent).toContain("I'm not freaked out by, but it's...");
    });
  });

  it("reuses the honesty-card empty-state treatment for a zero-line clip", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue({ ...META, clip_id: "03_2a_take", dialogue_count: 0 });
    mockGetClipDialogue.mockResolvedValue([]);

    const { container } = renderAt("03_2a_take");

    await screen.findByText("EMPTY");
    expect(screen.getByText(/No speech detected/)).toBeInTheDocument();
    expect(container.querySelector(".viewer__transcript-empty")).not.toBeNull();
    expect(screen.getByText("0 LINES · GEMINI")).toBeInTheDocument();
  });

  it("header shows the real line count", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);

    renderAt("01_1b_take");

    expect(await screen.findByText("2 LINES · GEMINI")).toBeInTheDocument();
  });

  it("shows a not-found state when the clip isn't indexed", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/does_not_exist.mp4");
    mockGetClipMeta.mockResolvedValue(null);
    mockGetClipDialogue.mockResolvedValue(null);

    renderAt("does_not_exist");

    expect(await screen.findByText(/Clip not found/)).toBeInTheDocument();
  });

  it("Circle take is a real write, not a disabled stub", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);
    mockSetCircled.mockResolvedValue(true);

    renderAt("01_1b_take");

    const btn = await screen.findByRole("button", { name: "Circle take" });
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);

    expect(mockSetCircled).toHaveBeenCalledWith("01_1b_take", true);
    expect(await screen.findByRole("button", { name: "Circled ✓" })).toBeInTheDocument();
  });

  it("reverts the optimistic circled state if the write fails", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);
    mockSetCircled.mockResolvedValue(null);

    renderAt("01_1b_take");

    const btn = await screen.findByRole("button", { name: "Circle take" });
    fireEvent.click(btn);

    expect(await screen.findByRole("button", { name: "Circled ✓" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Circle take" })).toBeInTheDocument();
  });

  it("omits LENS and SOUND from the metadata strip — no backing columns exist", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    mockGetClipDialogue.mockResolvedValue(LINES);

    renderAt("01_1b_take");

    await screen.findByText("SCENE");
    expect(screen.queryByText("LENS")).not.toBeInTheDocument();
    expect(screen.queryByText("SOUND")).not.toBeInTheDocument();
  });
});
