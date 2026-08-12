import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ClipPlayer } from "./ClipPlayer";
import { getClipUrl } from "../api";
import type { ActiveClip } from "../types";

vi.mock("../api", () => ({
  getClipUrl: vi.fn(),
}));

const mockGetClipUrl = vi.mocked(getClipUrl);

beforeEach(() => {
  mockGetClipUrl.mockReset();
  // jsdom's HTMLMediaElement.play() is not implemented and would otherwise
  // reject with a TypeError that escapes the component's own .catch(() => {}).
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
});

describe("ClipPlayer", () => {
  it("shows an empty state when no clip is active", () => {
    render(<ClipPlayer active={null} />);
    expect(screen.getByText(/No clip selected/)).toBeInTheDocument();
  });

  it("loads the signed url for the active clip and renders a video element", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip_1.mp4");
    const active: ActiveClip = { clipId: "clip_1", seekSeconds: 4, nonce: 1 };

    const { container } = render(<ClipPlayer active={active} />);

    await waitFor(() => expect(mockGetClipUrl).toHaveBeenCalledWith("clip_1"));
    await waitFor(() =>
      expect(container.querySelector("video")).toHaveAttribute(
        "src",
        "https://signed.example/clip_1.mp4"
      )
    );
    expect(screen.getByText("clip_1")).toBeInTheDocument();
  });

  it("renders the resilience fallback message when the <video> element errors", async () => {
    mockGetClipUrl.mockResolvedValue("https://signed.example/clip_1.mp4");
    const active: ActiveClip = { clipId: "clip_1", seekSeconds: 0, nonce: 1 };

    const { container } = render(<ClipPlayer active={active} />);

    await waitFor(() => expect(container.querySelector("video")).not.toBeNull());
    const video = container.querySelector("video");
    if (!video) throw new Error("video element did not render");

    fireEvent.error(video);

    expect(
      await screen.findByText(/Playback failed — the signed URL may have expired\./)
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
  });

  it("shows a load error when fetching the signed url fails", async () => {
    mockGetClipUrl.mockRejectedValue(new Error("network down"));
    const active: ActiveClip = { clipId: "clip_1", seekSeconds: 0, nonce: 1 };

    render(<ClipPlayer active={active} />);

    expect(await screen.findByText(/network down/)).toBeInTheDocument();
  });
});
