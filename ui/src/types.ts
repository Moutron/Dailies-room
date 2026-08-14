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

/** One query a tool ran to produce its result — table(s) touched, row count,
 * elapsed time, and the rendered SQL. `row_count` is absent when the query
 * failed, in which case `error` carries why. Real values only, captured at
 * the query call site (agent/tools/_evidence.py) — never reconstructed. */
export interface QueryEvidence {
  table: string;
  sql: string;
  elapsed_ms: number;
  row_count?: number;
  error?: string;
}

/** One row from search_dialogue / search_visuals / get_coverage / compare_takes.
 * Shapes differ per tool; only clip_id + timecode_in/out are guaranteed
 * when present, so everything else is read defensively. */
export interface ResultRow {
  clip_id?: string;
  scene?: string;
  slate?: string;
  take?: number;
  reel?: string;
  duration_s?: number;
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
  unmatched_expected?: string[];
  error?: string;
  error_type?: "unreachable" | "embedding_mismatch";
  [key: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  toolEvents: ToolEvent[];
  /** Query evidence for this turn's tool calls, in the order it arrived. */
  evidence: QueryEvidence[];
  streaming: boolean;
  errorText?: string;
  /** Set instead of errorText when the 429 came with a real retry window —
   * rendered as an expected-condition notice, not an error. */
  rateLimitedSeconds?: number;
}

/** The composer's real "CONTEXT KEPT" readout — the scene/slate the last
 * successful answer was actually about, read off its tool result rows. */
export interface SessionContext {
  scene: string;
  slate?: string;
}

/** One real turn in the current session, for the rail's "This session" list. */
export interface SessionTurn {
  id: string;
  text: string;
  active: boolean;
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

/** GET /clip/{clip_id}/meta — ui/server/clip_meta.py. Real slate metadata
 * for the viewer; LENS and SOUND have no backing columns and are
 * intentionally absent here, not just unrendered. */
export interface ClipMeta {
  clip_id: string;
  scene: string;
  slate: string;
  take: number;
  location: string;
  day_night: string;
  duration_s: number;
  reel: string;
  /** ISO-ish timestamp string from ClickHouse's DateTime column — real
   * ingest time, used by clip detail's metadata strip. */
  ingested_at: string;
  /** Source timecode (seconds) at the clip's first frame — real, from
   * clips.tc_start_s (agent/tools/search.py's same `offset_s`). Lets clip
   * detail render absolute source timecode, matching the takes table's
   * timecode_in/out rather than a clip-relative 00:00:00:00. */
  tc_start_s: number;
  shot_type: string | null;
  camera_movement: string | null;
  description: string | null;
  notable_elements: string[] | null;
  /** Real line count from the `dialogue` table — drives the viewer's empty
   * transcript state. 0 is a genuine finding, not a missing value. */
  dialogue_count: number;
  /** Real state from `circled_takes` (ui/server/circle.py) — the product's
   * first write path. */
  circled: boolean;
}

/** GET /clip/{clip_id}/dialogue — ui/server/clip_meta.py's clip_dialogue().
 * One row per real line, in playback order. Used by clip detail's
 * transcript panel and the player's dialogue-region overlay. */
export interface DialogueLine {
  segment_idx: number;
  start_s: number;
  end_s: number;
  speaker: string;
  text: string;
  delivery: string;
}

/** GET /stats — real, countable index-wide numbers. */
export interface IndexStats {
  clip_count: number;
  total_duration_s: number;
}

/** One row of GET /coverage/matrix — a real (scene, slate), one clip-id
 * array per shot-size column (ui/server/coverage_matrix.py's SHOT_COLUMNS
 * mapping). An empty array is a real gap, not a loading state. */
export interface CoverageMatrixRow {
  scene: string;
  slate: string;
  take: number;
  location: string;
  day_night: string;
  description: string;
  cells: Record<string, string[]>;
  unknown_clip_ids: string[];
  no_visuals_clip_ids: string[];
  has_tight_coverage: boolean;
  status: "COMPLETE" | "NO TIGHT COVERAGE";
  /** ui/server/coverage_matrix.py's richer gap label, or null on a
   * COMPLETE row — see that module's docstring for the mapping. */
  classification: ShotListClassification | null;
}

/** ui/server/shot_list.py's classification vocabulary — Screen #1g's
 * violet provenance pill. */
export type ShotListClassification = "coverage gap" | "wide coverage only" | "never appeared";

/** GET /coverage/matrix — ui/server/coverage_matrix.py's coverage_matrix().
 * `sql` is the real, finalized query that produced every row — shown on
 * hover over a status label, never reconstructed. */
export interface CoverageMatrix {
  columns: string[];
  rows: CoverageMatrixRow[];
  stats: { takes_printed: number; scenes: number; gaps_flagged: number };
  gap_scenes: string[];
  headline: string;
  sql: string;
}

/** One row of GET /clips — ui/server/clip_list.py's clip_list(). Real take
 * is not a unique per-clip label (all three S01 clips share
 * scene=S01/slate=1A/take=1) — key and display by clip_id. `shot_type` is
 * the raw 8-value enum value (or null, for a clip with no visuals row);
 * ui/src/agentCopy.ts's shotTypeLabel() maps it to the design's WIDE/MED/
 * MCU/CU/INSERT bucket for display. */
export interface ClipListItem {
  clip_id: string;
  reel: string;
  scene: string;
  slate: string;
  take: number;
  duration_s: number;
  shot_type: string | null;
  circled: boolean;
}

/** GET /shot-list/rows — ui/server/shot_list.py's list_rows(). Generated
 * live from the real coverage aggregate every read, never a fixture;
 * `selected` is the one piece of real, persisted user state. */
export interface ShotListRow {
  row_id: string;
  title: string;
  qualifier: string;
  reason: string;
  source_clip: string;
  classification: ShotListClassification;
  selected: boolean;
}

/** One row of GET /ingest/summary — ui/server/ingest.py's ingest_summary().
 * Every clip in this index is uniformly READY -- there is no in-flight or
 * queued state to render (see that module's docstring for why). */
export interface IngestClip {
  clip_id: string;
  duration_s: number;
  ingested_at: string;
  dialogue_count: number;
  state: "READY";
}

/** GET /ingest/summary — Screen #6's real pipeline-index state.
 * `most_recent_ingested_at` replaces the mockup's fake "N CLIPS IN FLIGHT"
 * live badge. AVG PER CLIP has no field here at all -- per-clip ingest
 * duration is recorded nowhere in this schema, so it's omitted rather than
 * fabricated. */
export interface IngestSummary {
  clips: IngestClip[];
  indexed_today: number;
  embeddings: number;
  most_recent_ingested_at: string | null;
}

/** One result of GET /search — ui/server/search.py's browse_search(). A
 * dialogue hit carries a speaker and a real performance-note (delivery); a
 * visual hit has neither, and its note is the real camera_movement instead
 * — `note_label` says which so the UI never mislabels one as the other.
 * `score` is a real cosineDistance-derived similarity (0..1, higher =
 * better match) for "semantic" mode, and always null for "keyword" mode —
 * an ILIKE match isn't ranked, so the UI must not show a badge for it. */
export interface SearchHit {
  kind: "dialogue" | "visual";
  clip_id: string;
  scene: string | null;
  take: number | null;
  reel: string | null;
  timecode_in: string | null;
  quote: string;
  speaker: string | null;
  note: string | null;
  note_label: string;
  score: number | null;
}

/** GET /search response. */
export interface SearchResponse {
  query: string;
  mode: "semantic" | "keyword";
  hits: SearchHit[];
}
