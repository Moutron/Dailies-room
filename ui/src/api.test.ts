import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getClipMeta,
  getClipUrl,
  getPosterUrl,
  getStats,
  getThumbnails,
  rowsFromToolResult,
  streamChat,
  timecodeToSeconds,
} from "./api";

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

describe("getPosterUrl", () => {
  it("builds a deterministic /posters path, no fetch involved", () => {
    expect(getPosterUrl("01_1a_take")).toBe("/posters/01_1a_take.jpg");
  });

  it("encodes the clip id", () => {
    expect(getPosterUrl("clip/weird id")).toBe("/posters/clip%2Fweird%20id.jpg");
  });
});

describe("getClipMeta", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the metadata on success", async () => {
    const meta = { clip_id: "01_1a_take", scene: "S01" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(meta) }));
    await expect(getClipMeta("01_1a_take")).resolves.toEqual(meta);
  });

  it("returns null on failure instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(getClipMeta("missing")).resolves.toBeNull();
  });
});

describe("getStats", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns real stats on success", async () => {
    const stats = { clip_count: 6, total_duration_s: 29.83 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(stats) }));
    await expect(getStats()).resolves.toEqual(stats);
  });

  it("returns null on failure instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(getStats()).resolves.toBeNull();
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

  it("parses a tool_evidence frame", async () => {
    const frames =
      'event: tool_evidence\ndata: {"tool": "search_dialogue", "queries": [{"table": "dialogue", "sql": "SELECT 1", "elapsed_ms": 1.2, "row_count": 3}]}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, body: bodyFromFrames(frames) })
    );

    const events = [];
    for await (const event of streamChat("hi", "session-1")) {
      events.push(event);
    }

    expect(events).toEqual([
      {
        type: "tool_evidence",
        tool: "search_dialogue",
        queries: [{ table: "dialogue", sql: "SELECT 1", elapsed_ms: 1.2, row_count: 3 }],
      },
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

  it("yields a rate_limited event with the real Retry-After seconds on 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        body: null,
        headers: { get: (name: string) => (name === "Retry-After" ? "3" : null) },
      })
    );

    const events = [];
    for await (const event of streamChat("hi", "session-1")) {
      events.push(event);
    }

    expect(events).toEqual([{ type: "rate_limited", retryAfterSeconds: 3 }]);
  });

  it("defaults retryAfterSeconds to 0 when the header is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        body: null,
        headers: { get: () => null },
      })
    );

    const events = [];
    for await (const event of streamChat("hi", "session-1")) {
      events.push(event);
    }

    expect(events).toEqual([{ type: "rate_limited", retryAfterSeconds: 0 }]);
  });
});
