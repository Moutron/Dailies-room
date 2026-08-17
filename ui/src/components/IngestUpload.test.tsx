import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IngestUpload } from "./IngestUpload";
import { uploadFootage } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    uploadFootage: vi.fn(),
  };
});

const mockUploadFootage = vi.mocked(uploadFootage);

function mp4File(name = "clip.mp4") {
  return new File(["fake-mp4-bytes"], name, { type: "video/mp4" });
}

function jpgFile(name: string) {
  return new File(["fake-jpg-bytes"], name, { type: "image/jpeg" });
}

async function fillRequiredMeta(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByPlaceholderText("clip_id *"), "clip_1");
  await user.type(screen.getByPlaceholderText("scene *"), "S01");
  await user.type(screen.getByPlaceholderText("slate *"), "1A");
  await user.type(screen.getByPlaceholderText("take *"), "2");
}

beforeEach(() => {
  mockUploadFootage.mockReset();
});

describe("IngestUpload", () => {
  it("submit is disabled until required fields and a file are both present", async () => {
    const user = userEvent.setup();
    render(<IngestUpload onUploaded={vi.fn()} />);

    const submit = screen.getByRole("button", { name: /upload/i });
    expect(submit).toBeDisabled();

    await fillRequiredMeta(user);
    expect(submit).toBeDisabled(); // metadata alone isn't enough -- still no file

    const fileInput = screen.getByLabelText("MP4 file");
    await user.upload(fileInput, mp4File());

    expect(submit).not.toBeDisabled();
  });

  it("a file alone, with metadata missing, is not enough to enable submit", async () => {
    const user = userEvent.setup();
    render(<IngestUpload onUploaded={vi.fn()} />);

    const fileInput = screen.getByLabelText("MP4 file");
    await user.upload(fileInput, mp4File());

    expect(screen.getByRole("button", { name: /upload/i })).toBeDisabled();
  });

  it("mode toggle swaps the file input and shows/hides the fps + duration readout", async () => {
    const user = userEvent.setup();
    render(<IngestUpload onUploaded={vi.fn()} />);

    expect(screen.getByLabelText("MP4 file")).toBeInTheDocument();
    expect(screen.queryByText(/FRAMES/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "MP4" }));

    expect(screen.getByLabelText("Frame files")).toBeInTheDocument();
    expect(screen.queryByLabelText("MP4 file")).not.toBeInTheDocument();
    expect(screen.getByText("0 FRAMES")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "FRAME SEQUENCE" }));

    expect(screen.getByLabelText("MP4 file")).toBeInTheDocument();
    expect(screen.queryByText(/FRAMES/)).not.toBeInTheDocument();
  });

  it("frame count and computed duration update as frames are chosen", async () => {
    const user = userEvent.setup();
    render(<IngestUpload onUploaded={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "MP4" }));
    const fileInput = screen.getByLabelText("Frame files");
    await user.upload(fileInput, [jpgFile("frame_1.jpg"), jpgFile("frame_2.jpg")]);

    expect(screen.getByText("2 FRAMES")).toBeInTheDocument();
    // 2 frames / 24 fps default = 0.08s
    expect(screen.getByText("0.08s")).toBeInTheDocument();
  });

  it("server error text is rendered as-is, no generic fallback", async () => {
    const user = userEvent.setup();
    mockUploadFootage.mockResolvedValue({
      ok: false,
      error: "clip_id must match '^[a-z0-9_]{1,64}$', got 'Bad Clip!'.",
    });

    render(<IngestUpload onUploaded={vi.fn()} />);
    await fillRequiredMeta(user);
    await user.upload(screen.getByLabelText("MP4 file"), mp4File());
    await user.click(screen.getByRole("button", { name: /upload/i }));

    await waitFor(() =>
      expect(
        screen.getByText("clip_id must match '^[a-z0-9_]{1,64}$', got 'Bad Clip!'.")
      ).toBeInTheDocument()
    );
  });

  it("on success, refetches the summary and clears the form", async () => {
    const user = userEvent.setup();
    const onUploaded = vi.fn();
    mockUploadFootage.mockResolvedValue({
      ok: true,
      clip: { clip_id: "clip_1", duration_s: 5, ingested_at: "now", dialogue_count: 0, state: "READY" },
    });

    render(<IngestUpload onUploaded={onUploaded} />);
    await fillRequiredMeta(user);
    await user.upload(screen.getByLabelText("MP4 file"), mp4File());
    await user.click(screen.getByRole("button", { name: /upload/i }));

    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
    expect((screen.getByPlaceholderText("clip_id *") as HTMLInputElement).value).toBe("");
    expect((screen.getByPlaceholderText("scene *") as HTMLInputElement).value).toBe("");
    expect(screen.getByRole("button", { name: /upload/i })).toBeDisabled();
  });

  it("forwards the chosen mode's payload shape to uploadFootage", async () => {
    const user = userEvent.setup();
    mockUploadFootage.mockResolvedValue({
      ok: true,
      clip: { clip_id: "clip_1", duration_s: 5, ingested_at: "now", dialogue_count: 0, state: "READY" },
    });

    render(<IngestUpload onUploaded={vi.fn()} />);
    await fillRequiredMeta(user);
    const file = mp4File();
    await user.upload(screen.getByLabelText("MP4 file"), file);
    await user.click(screen.getByRole("button", { name: /upload/i }));

    await waitFor(() => expect(mockUploadFootage).toHaveBeenCalledTimes(1));
    const [meta, payload] = mockUploadFootage.mock.calls[0];
    expect(meta.clipId).toBe("clip_1");
    expect(meta.scene).toBe("S01");
    expect(payload).toEqual({ mode: "mp4", file });
  });
});
