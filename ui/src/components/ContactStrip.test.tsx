import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ContactStrip } from "./ContactStrip";
import { getThumbnails } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, getThumbnails: vi.fn() };
});

const mockGetThumbnails = vi.mocked(getThumbnails);

beforeEach(() => {
  mockGetThumbnails.mockReset();
});

describe("ContactStrip", () => {
  it("renders nothing once loaded with zero frames", async () => {
    mockGetThumbnails.mockResolvedValue([]);
    const { container } = render(<ContactStrip clipId="clip_1" onSeek={vi.fn()} />);

    await waitFor(() => expect(mockGetThumbnails).toHaveBeenCalled());
    expect(container.querySelector(".contact-strip")).toBeNull();
  });

  it("renders one button per frame with its timecode", async () => {
    mockGetThumbnails.mockResolvedValue([
      { file: "clip_1_001.jpg", start_s: 0, timecode: "00:00:00:00" },
      { file: "clip_1_002.jpg", start_s: 2, timecode: "00:00:02:00" },
    ]);
    render(<ContactStrip clipId="clip_1" onSeek={vi.fn()} />);

    const buttons = await screen.findAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(screen.getByText("00:00:02:00")).toBeInTheDocument();
  });

  it("calls onSeek with the clip id and seconds derived from the timecode", async () => {
    mockGetThumbnails.mockResolvedValue([
      { file: "clip_1_002.jpg", start_s: 2, timecode: "00:00:02:00" },
    ]);
    const onSeek = vi.fn();
    render(<ContactStrip clipId="clip_1" onSeek={onSeek} />);

    const button = await screen.findByRole("button");
    fireEvent.click(button);

    expect(onSeek).toHaveBeenCalledWith("clip_1", 2);
  });
});
