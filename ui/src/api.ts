import type { ResultRow, Thumbnail } from "./types";

const FPS = 24;

/** "HH:MM:SS:FF" -> seconds. Inverse of agent/tools/search.py's timecode(). */
export function timecodeToSeconds(tc: string): number {
  const [h, m, s, f] = tc.split(":").map(Number);
  return h * 3600 + m * 60 + s + f / FPS;
}

export type ChatEvent =
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; result: unknown }
  | { type: "message"; text: string; final: boolean }
  | { type: "error"; message: string }
  | { type: "done" };

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
