import type {
  ClipListItem,
  ClipMeta,
  CoverageMatrix,
  DialogueLine,
  IndexStats,
  IngestSummary,
  QueryEvidence,
  ResultRow,
  SearchResponse,
  ShotListRow,
  Thumbnail,
} from "./types";

const FPS = 24;

/** "HH:MM:SS:FF" -> seconds. Inverse of agent/tools/search.py's timecode(). */
export function timecodeToSeconds(tc: string): number {
  const [h, m, s, f] = tc.split(":").map(Number);
  return h * 3600 + m * 60 + s + f / FPS;
}

/** seconds -> "HH:MM:SS:FF". Mirrors agent/tools/search.py's timecode() —
 * same math, client side, so clip detail can render a line's real source
 * timecode without a round trip for every row. `offsetS` is the clip's
 * tc_start_s (source timecode at frame zero); omit it for a clip-relative
 * readout. */
export function secondsToTimecode(seconds: number, offsetS = 0): string {
  const totalFrames = Math.round((seconds + offsetS) * FPS);
  const frames = totalFrames % FPS;
  const totalSeconds = Math.floor(totalFrames / FPS);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return [
    pad(Math.floor(totalSeconds / 3600)),
    pad(Math.floor((totalSeconds % 3600) / 60)),
    pad(totalSeconds % 60),
    pad(frames),
  ].join(":");
}

export type ChatEvent =
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; result: unknown }
  | { type: "tool_evidence"; tool: string; queries: QueryEvidence[] }
  | { type: "message"; text: string; final: boolean }
  | { type: "error"; message: string }
  | { type: "rate_limited"; retryAfterSeconds: number }
  | { type: "done"; turn_count?: number };

/** Extracts the row list from an ADK function-response payload.
 * ADK wraps a tool's return value as {"result": <return value>}; our tools
 * return either a list[dict] or (on failure) a list with a single
 * {"error": "..."} dict — both normalize to ResultRow[] here. */
export function rowsFromToolResult(result: unknown): { rows: ResultRow[]; isError: boolean } {
  const payload = (result as { result?: unknown })?.result ?? result;
  const rows: ResultRow[] = Array.isArray(payload) ? payload : [];
  const isError = rows.length === 1 && typeof rows[0]?.error === "string";
  return { rows, isError };
}

/** Streams one chat turn, parsing the backend's `event:`/`data:` SSE frames
 * from a fetch() ReadableStream (EventSource can't do POST bodies). */
export async function* streamChat(
  message: string,
  sessionId: string,
  signal?: AbortSignal
): AsyncGenerator<ChatEvent> {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });
  if (!res.ok || !res.body) {
    if (res.status === 429) {
      const header = res.headers?.get?.("Retry-After");
      const retryAfterSeconds = header ? Number(header) : 0;
      yield { type: "rate_limited", retryAfterSeconds: Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : 0 };
      return;
    }
    yield { type: "error", message: `The server returned an unexpected response (${res.status}).` };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event = parseFrame(frame);
      if (event) yield event;
    }
  }
}

function parseFrame(frame: string): ChatEvent | null {
  let type = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!type) return null;
  const parsed = data ? JSON.parse(data) : {};
  return { type, ...parsed } as ChatEvent;
}

export async function getClipUrl(clipId: string): Promise<string> {
  const res = await fetch(`/clip/${encodeURIComponent(clipId)}/url`);
  if (!res.ok) throw new Error(`Could not get a playback URL for ${clipId} (${res.status}).`);
  const data = await res.json();
  return data.url;
}

export async function getThumbnails(clipId: string): Promise<Thumbnail[]> {
  const res = await fetch(`/clip/${encodeURIComponent(clipId)}/thumbnails`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.frames ?? [];
}

/** URL for a clip's 960x540 letterboxed poster frame (pipeline/posters.py),
 * served at /posters/{clip_id}.jpg — filenames are deterministic, so this
 * needs no round trip the way getClipUrl's signed URL does. */
export function getPosterUrl(clipId: string): string {
  return `/posters/${encodeURIComponent(clipId)}.jpg`;
}

export async function getClipMeta(clipId: string): Promise<ClipMeta | null> {
  const res = await fetch(`/clip/${encodeURIComponent(clipId)}/meta`);
  if (!res.ok) return null;
  return res.json();
}

/** Real dialogue rows for clip detail's transcript and dialogue-region
 * overlay. An indexed clip with zero lines (all three S03 clips) returns
 * an empty array, not null — only a clip that isn't indexed at all does. */
export async function getClipDialogue(clipId: string): Promise<DialogueLine[] | null> {
  const res = await fetch(`/clip/${encodeURIComponent(clipId)}/dialogue`);
  if (!res.ok) return null;
  const data = await res.json();
  return data.lines ?? [];
}

export async function getStats(): Promise<IndexStats | null> {
  const res = await fetch("/stats");
  if (!res.ok) return null;
  return res.json();
}

/** Real scene/slate x shot-size grid for Screen #1c — GET /coverage/matrix
 * (ui/server/coverage_matrix.py). */
export async function getCoverageMatrix(): Promise<CoverageMatrix | null> {
  const res = await fetch("/coverage/matrix");
  if (!res.ok) return null;
  return res.json();
}

/** Real flat clip list for Screen #1d's contact sheet — GET /clips
 * (ui/server/clip_list.py). `reels`/`shotTypes` are additive filters
 * (OR within each, ANDed together), mirrored into the URL by the caller. */
export async function getClipList(
  reels: string[] = [],
  shotTypes: string[] = []
): Promise<ClipListItem[]> {
  const params = new URLSearchParams();
  for (const r of reels) params.append("reel", r);
  for (const s of shotTypes) params.append("shot_type", s);
  const qs = params.toString();
  const res = await fetch(qs ? `/clips?${qs}` : "/clips");
  if (!res.ok) return [];
  const data = await res.json();
  return data.clips ?? [];
}

/** Real search results for Screen #1d's search bar — GET /search
 * (ui/server/search.py). `mode` is "semantic" (cosineDistance, real score
 * badge) or "keyword" (ILIKE, no score). */
export async function searchClips(query: string, mode: "semantic" | "keyword"): Promise<SearchResponse | null> {
  const params = new URLSearchParams({ q: query, mode });
  const res = await fetch(`/search?${params.toString()}`);
  if (!res.ok) return null;
  return res.json();
}

/** The product's first write path — POST /clip/{clip_id}/circle
 * (ui/server/circle.py). Returns the clip's new circled state, or null on
 * a real failure (e.g. the clip isn't indexed). */
export async function setCircled(clipId: string, circled: boolean): Promise<boolean | null> {
  const res = await fetch(`/clip/${encodeURIComponent(clipId)}/circle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ circled }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.circled;
}

/** Screen #1g's rows — GET /shot-list/rows (ui/server/shot_list.py).
 * Generated live from the real coverage aggregate on every call, never a
 * fixture. */
export async function getShotListRows(): Promise<ShotListRow[]> {
  const res = await fetch("/shot-list/rows");
  if (!res.ok) return [];
  const data = await res.json();
  return data.rows ?? [];
}

export async function setShotListRowSelected(rowId: string, selected: boolean): Promise<ShotListRow | null> {
  const res = await fetch(`/shot-list/rows/${encodeURIComponent(rowId)}/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected }),
  });
  if (!res.ok) return null;
  return res.json();
}

/** Screen #6's real pipeline-index state — GET /ingest/summary
 * (ui/server/ingest.py). Static explainer over the same tables the rest of
 * the app reads; every clip comes back READY. */
export async function getIngestSummary(): Promise<IngestSummary | null> {
  const res = await fetch("/ingest/summary");
  if (!res.ok) return null;
  return res.json();
}
