import { afterEach, describe, expect, it, vi } from "vitest";
import { getClipUrl, getThumbnails, rowsFromToolResult, streamChat, timecodeToSeconds } from "./api";

describe("timecodeToSeconds", () => {
  it("converts HH:MM:SS:FF back to seconds", () => {
    expect(timecodeToSeconds("00:00:00:00")).toBe(0);
    expect(timecodeToSeconds("00:01:30:00")).toBe(90);
  });

  it("is the inverse of the backend's timecode() at 24fps", () => {
    // 12 frames at 24fps = 0.5s
    expect(timecodeToSeconds("00:00:02:12")).toBeCloseTo(2.5, 5);
  });

  it("handles hour rollover", () => {
    expect(timecodeToSeconds("01:00:00:00")).toBe(3600);
  });
});

describe("rowsFromToolResult", () => {
  it("unwraps an ADK-style {result: [...]} payload", () => {
    const { rows, isError } = rowsFromToolResult({ result: [{ clip_id: "c1" }] });
    expect(rows).toEqual([{ clip_id: "c1" }]);
    expect(isError).toBe(false);
  });

  it("treats a bare array as the row list", () => {
    const { rows, isError } = rowsFromToolResult([{ clip_id: "c1" }]);
    expect(rows).toEqual([{ clip_id: "c1" }]);
    expect(isError).toBe(false);
  });

  it("detects a single-row error payload", () => {
    const { rows, isError } = rowsFromToolResult({ result: [{ error: "unreachable" }] });
    expect(rows).toEqual([{ error: "unreachable" }]);
    expect(isError).toBe(true);
  });

  it("treats a non-array payload as no rows", () => {
    const { rows, isError } = rowsFromToolResult({ result: null });
    expect(rows).toEqual([]);
    expect(isError).toBe(false);
  });
});

describe("getClipUrl", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the signed url on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ url: "https://signed.example/x.mp4" }),
      })
    );
    await expect(getClipUrl("clip_1")).resolves.toBe("https://signed.example/x.mp4");
  });

  it("throws with the status code on failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));
    await expect(getClipUrl("clip_1")).rejects.toThrow("502");
  });
});

describe("getThumbnails", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns frames on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ frames: [{ file: "a.jpg", start_s: 0, timecode: "00:00:00:00" }] }),
      })
    );
    const frames = await getThumbnails("clip_1");
    expect(frames).toHaveLength(1);
  });

  it("returns an empty list on failure instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(getThumbnails("clip_1")).resolves.toEqual([]);
  });
});

describe("streamChat", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function bodyFromFrames(frames: string): ReadableStream<Uint8Array> {
    const bytes = new TextEncoder().encode(frames);
    return new ReadableStream({
      start(controller) {
        controller.enqueue(bytes);
        controller.close();
      },
    });
  }

  it("parses SSE event/data frames into ChatEvents", async () => {
    const frames =
      'event: tool_call\ndata: {"tool": "search_dialogue", "args": {"query": "hi"}}\n\n' +
      'event: message\ndata: {"text": "hello", "final": true}\n\n' +
      "event: done\ndata: {}\n\n";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, body: bodyFromFrames(frames) })
    );

    const events = [];
    for await (const event of streamChat("hi", "session-1")) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "tool_call", tool: "search_dialogue", args: { query: "hi" } },
      { type: "message", text: "hello", final: true },
      { type: "done" },
    ]);
  });

  it("yields an error event when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, body: null }));

    const events = [];
    for await (const event of streamChat("hi", "session-1")) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "error", message: "The server returned an unexpected response (500)." },
    ]);
  });
});
