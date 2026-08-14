import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Viewer } from "./Viewer";
import { getClipMeta, getClipUrl } from "../api";
import type { ActiveClip, ClipMeta } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getClipUrl: vi.fn(),
    getClipMeta: vi.fn(),
  };
});

const mockGetClipUrl = vi.mocked(getClipUrl);
const mockGetClipMeta = vi.mocked(getClipMeta);

const META: ClipMeta = {
  clip_id: "01_1a_take",
  scene: "S01",
  slate: "1A",
  take: 1,
  location: "Amsterdam canal bridge",
  day_night: "DAY",
  duration_s: 5.5,
  reel: "A002",
  ingested_at: "2026-08-14 12:30:27",
  tc_start_s: 0,
  shot_type: "medium",
  camera_movement: "static",
  description: "Two people talk on a bridge.",
  notable_elements: ["bridge railing", "canal"],
  dialogue_count: 1,
  circled: false,
};

beforeEach(() => {
  mockGetClipUrl.mockReset();
  mockGetClipMeta.mockReset();
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
});

describe("Viewer", () => {
  it("shows a no-clip placeholder when nothing is active", () => {
    render(<Viewer active={null} />);
    expect(screen.getByText("Click a result to play it here.")).toBeInTheDocument();
  });

  it("loads the signed url and metadata for the active clip", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    const active: ActiveClip = { clipId: "01_1a_take", seekSeconds: 4, nonce: 1 };

    const { container } = render(<Viewer active={active} />);

    await waitFor(() => expect(mockGetClipUrl).toHaveBeenCalledWith("01_1a_take"));
    await waitFor(() =>
      expect(container.querySelector("video")).toHaveAttribute(
        "src",
        "https://signed.example/clip.mp4"
      )
    );
    expect(await screen.findByText("S01 — AMSTERDAM CANAL BRIDGE, DAY")).toBeInTheDocument();
    expect(screen.getByText("1A / 1")).toBeInTheDocument();
    expect(screen.getByText("static")).toBeInTheDocument();
    expect(screen.getByText("Two people talk on a bridge.")).toBeInTheDocument();
    expect(screen.getByText("bridge railing")).toBeInTheDocument();
  });

  it("never renders LENS or SOUND fields — no backing data exists for them", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    const active: ActiveClip = { clipId: "01_1a_take", seekSeconds: 0, nonce: 1 };

    render(<Viewer active={active} />);

    await screen.findByText("SLATE / TAKE");
    expect(screen.queryByText("LENS")).not.toBeInTheDocument();
    expect(screen.queryByText("SOUND")).not.toBeInTheDocument();
  });

  it("calls onMetaLoaded with the fetched metadata", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    const onMetaLoaded = vi.fn();
    const active: ActiveClip = { clipId: "01_1a_take", seekSeconds: 0, nonce: 1 };

    render(<Viewer active={active} onMetaLoaded={onMetaLoaded} />);

    await waitFor(() => expect(onMetaLoaded).toHaveBeenCalledWith(META));
  });

  it("renders the resilience fallback message when the <video> element errors", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    const active: ActiveClip = { clipId: "01_1a_take", seekSeconds: 0, nonce: 1 };

    const { container } = render(<Viewer active={active} />);

    await waitFor(() => expect(container.querySelector("video")).not.toBeNull());
    const video = container.querySelector("video");
    if (!video) throw new Error("video element did not render");

    fireEvent.error(video);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
  });

  it("shows a load error when fetching the signed url fails", async () => {
    mockGetClipUrl.mockRejectedValue(new Error("network down"));
    mockGetClipMeta.mockResolvedValue(META);
    const active: ActiveClip = { clipId: "01_1a_take", seekSeconds: 0, nonce: 1 };

    render(<Viewer active={active} />);

    expect(await screen.findByText("network down")).toBeInTheDocument();
  });

  it("toggles play/pause on the custom transport button", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip.mp4");
    mockGetClipMeta.mockResolvedValue(META);
    const active: ActiveClip = { clipId: "01_1a_take", seekSeconds: 0, nonce: 1 };

    const { container } = render(<Viewer active={active} />);
    await waitFor(() => expect(container.querySelector("video")).not.toBeNull());

    const playButton = screen.getByRole("button", { name: "Play" });
    fireEvent.click(playButton);

    const video = container.querySelector("video")!;
    fireEvent.play(video);

    expect(await screen.findByRole("button", { name: "Pause" })).toBeInTheDocument();
  });
});
