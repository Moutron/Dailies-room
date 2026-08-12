export interface ToolCallEvent {
  kind: "call";
  tool: string;
  args: Record<string, unknown>;
}

export interface ToolResultEvent {
  kind: "result";
  tool: string;
  rows: ResultRow[];
  isError: boolean;
}

export type ToolEvent = ToolCallEvent | ToolResultEvent;

/** One row from search_dialogue / search_visuals / get_coverage / compare_takes.
 * Shapes differ per tool; only clip_id + timecode_in/out are guaranteed
 * when present, so everything else is read defensively. */
export interface ResultRow {
  clip_id?: string;
  scene?: string;
  slate?: string;
  take?: number;
  timecode_in?: string;
  timecode_out?: string;
  speaker?: string;
  text?: string;
  delivery?: string;
  description?: string;
  summary?: string;
  shot_type?: string;
  technical_notes?: string[];
  dominant_mood?: string;
  dialogue?: ResultRow[];
  never_appeared?: string[];
  no_tight_shot?: string[];
  wide_coverage?: string[];
  error?: string;
  [key: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  toolEvents: ToolEvent[];
  streaming: boolean;
  errorText?: string;
}

export interface Thumbnail {
  file: string;
  start_s: number;
  timecode: string;
}

export interface ActiveClip {
  clipId: string;
  seekSeconds: number;
  /** bumped on every seek request so effects re-fire even for the same clip+time */
  nonce: number;
}
