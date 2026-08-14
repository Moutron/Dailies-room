import type { ChatMessage, ClipMeta, ResultRow, SessionContext, ToolEvent } from "./types";

const SHOT_LABELS: Record<string, string> = {
  extreme_wide: "WIDE",
  wide: "WIDE",
  medium: "MED",
  medium_close: "MCU",
  close: "CU",
  extreme_close: "CU",
  insert: "INSERT",
};

/** shot_type enum value -> the design's short on-screen label. Missing or
 * unrecognized values fall back to an em dash — this is chrome, not data,
 * so a gap in coverage (compare_takes doesn't select shot_type) should
 * never be dressed up to look like a value that was actually observed. */
export function shotTypeLabel(shotType?: string): string {
  if (!shotType) return "—";
  return SHOT_LABELS[shotType] ?? shotType.toUpperCase();
}

/** seconds -> "1:55". Whole seconds only — this is a duration readout, not
 * a seek target, so frame precision isn't the point. */
export function formatDuration(seconds?: number): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** SCENE field: real scene + location + day/night, composed — never the
 * mockup's fabricated "07 — BRIDGE, NIGHT". Shared by the Ask viewer and
 * clip detail so the two screens never drift on how this is built. */
export function sceneLabel(meta: Pick<ClipMeta, "scene" | "location" | "day_night">): string {
  return `${meta.scene} — ${meta.location.toUpperCase()}, ${meta.day_night.toUpperCase()}`;
}

/** seconds -> "00:00:30" (HH:MM:SS) — the top bar's TRT readout. Matches
 * the mockup's HH:MM:SS shape, but for this six-clip index that's ~30
 * seconds, not the mockup's fictional 04:11:38 — real numbers, not the
 * demo copy's scale. */
export function formatTRT(seconds: number): string {
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => n.toString().padStart(2, "0")).join(":");
}

type ResultEvent = Extract<ToolEvent, { kind: "result" }>;

/** The last non-error result this turn produced — the one the answer is
 * actually about, and what the takes table renders. A turn can call more
 * than one tool (e.g. search_visuals to resolve a scene, then
 * get_coverage on it); showing every tool's raw rows stacked together
 * would mean rendering two differently-shaped tables as one, so only the
 * last is shown. */
export function lastResult(toolEvents: ToolEvent[]): ResultEvent | null {
  for (let i = toolEvents.length - 1; i >= 0; i--) {
    const e = toolEvents[i];
    if (e.kind === "result" && !e.isError) return e;
  }
  return null;
}

const RESULT_NOUNS: Record<string, string> = {
  search_dialogue: "line",
  search_visuals: "shot",
  get_coverage: "take",
  compare_takes: "take",
};

/** "AGENT · N TAKES FOUND" — a real count, noun picked from whichever tool
 * produced it. The mockup's literal copy ("TAKES FOUND") is specific to a
 * coverage query; other tools get their own honest noun rather than being
 * forced into "takes" when they returned lines or shots instead. */
export function resultCountLabel(toolEvents: ToolEvent[]): string | null {
  const result = lastResult(toolEvents);
  if (!result) return null;
  const count = result.rows.length;
  if (count === 0) return "NOTHING FOUND";
  const noun = RESULT_NOUNS[result.tool] ?? "result";
  return `${count} ${noun.toUpperCase()}${count === 1 ? "" : "S"} FOUND`;
}

const SUBSTAGE_LABELS: Record<string, string> = {
  search_dialogue: "searching dialogue…",
  search_visuals: "searching visuals…",
  get_coverage: "reading coverage…",
  compare_takes: "comparing takes…",
};

/** What to show in place of the agent header while a turn is pending,
 * driven by the tool_call events already emitted — never a spinner with
 * nothing behind it. */
export function substageLabel(toolEvents: ToolEvent[]): string {
  for (let i = toolEvents.length - 1; i >= 0; i--) {
    const e = toolEvents[i];
    if (e.kind === "call") return SUBSTAGE_LABELS[e.tool] ?? "searching the footage…";
  }
  return "searching the footage…";
}

/** "00:41:09:14" -> "00:41:09" — drops the frame field for the clarifying
 * card's option sub-label, matching the handoff's HH:MM:SS shape. Purely a
 * display trim of a real value, never a fabricated one. */
function shortTimecode(tc?: string): string | null {
  if (!tc) return null;
  const parts = tc.split(":");
  return parts.length === 4 ? parts.slice(0, 3).join(":") : tc;
}

export interface ClarifyingOption {
  clip_id?: string;
  slate: string;
  take: number;
  reel?: string;
  timecodeShort: string | null;
}

export interface ClarifyingQuestion {
  question: string;
  options: ClarifyingOption[];
  /** Only set when the candidate rows actually share a take number — never
   * the mockup's blanket "take numbers repeat across slates" claim, which
   * isn't true of this index (see DESIGN_IMPLEMENTATION_PLAN.md 1.3). */
  reason: string | null;
}

/** Detects a clarifying turn from the agent's own response — never a
 * hardcoded step in the flow. Fires only when the agent's answer reads as a
 * question AND this turn's last tool result actually returned more than one
 * distinct slate/take candidate to choose between; the options are exactly
 * those rows, not an invented list of three. */
export function detectClarifyingQuestion(m: ChatMessage): ClarifyingQuestion | null {
  const question = m.text.trim();
  if (!question.endsWith("?")) return null;

  const result = lastResult(m.toolEvents);
  if (!result) return null;

  const seen = new Set<string>();
  const options: ClarifyingOption[] = [];
  for (const row of result.rows) {
    if (row.slate == null || row.take == null) continue;
    const key = `${row.slate}/${row.take}`;
    if (seen.has(key)) continue;
    seen.add(key);
    options.push({
      clip_id: row.clip_id,
      slate: row.slate,
      take: row.take,
      reel: row.reel,
      timecodeShort: shortTimecode(row.timecode_in),
    });
  }
  if (options.length < 2) return null;

  const takeCounts = new Map<number, number>();
  for (const o of options) takeCounts.set(o.take, (takeCounts.get(o.take) ?? 0) + 1);
  const repeatedTakes = [...takeCounts.entries()]
    .filter(([, n]) => n > 1)
    .map(([take]) => take)
    .sort((a, b) => a - b);
  const scene = result.rows.find((r) => r.scene)?.scene;
  const reason =
    repeatedTakes.length && scene
      ? `Scene ${scene} has more than one take ${repeatedTakes.join(", ")} across different slates.`
      : null;

  return { question, options, reason };
}

export interface NoDialogueAnswer {
  headline: string;
  body: string | null;
  clip: ResultRow | null;
}

/** Splits the agent's real answer text into a headline (first sentence) and
 * the rest — never synthesized copy, just the model's own text laid out at
 * two type scales the way the handoff's honesty card does. */
function splitHeadline(text: string): { headline: string; body: string | null } {
  const match = text.match(/^(.*?[.!?])\s+(.*)$/s);
  if (!match) return { headline: text, body: null };
  const [, headline, rest] = match;
  return { headline, body: rest.trim() || null };
}

function extractTakeNumber(text?: string): number | null {
  const match = text?.match(/take\s*(\d+)/i);
  return match ? Number(match[1]) : null;
}

/** Detects the "no dialogue in this take" honesty state, and picks which
 * clip it's grounded in. Two real shapes produce this, both observed live:
 *  - search_dialogue itself returned zero rows (evidence: `dialogue · 0
 *    rows`) — the clip comes from whatever other tool this turn resolved it
 *    with.
 *  - compare_takes returned rows that each carry their own `dialogue: []`
 *    array (no separate zero-row evidence exists for this shape, since the
 *    query joins clips/dialogue/visuals in one round trip) — when it
 *    matched more than one take, the preceding question's take number picks
 *    the right one instead of defaulting to the first.
 * Without a resolvable clip this returns null and the turn renders as a
 * normal answer — never a card pointing at a take we can't actually name. */
export function detectNoDialogueAnswer(
  m: ChatMessage,
  precedingUserText?: string
): NoDialogueAnswer | null {
  const result = lastResult(m.toolEvents);
  if (!result) return null;

  const emptyDialogueRows = result.rows.filter(
    (r) => r.clip_id && Array.isArray(r.dialogue) && r.dialogue.length === 0
  );
  const zeroDialogueEvidence = m.evidence.some((e) => e.table === "dialogue" && e.row_count === 0);

  let clip: ResultRow | null = null;
  if (emptyDialogueRows.length > 0) {
    const wantedTake = extractTakeNumber(precedingUserText);
    clip = (wantedTake != null && emptyDialogueRows.find((r) => r.take === wantedTake)) || emptyDialogueRows[0];
  } else if (zeroDialogueEvidence) {
    clip = result.rows.find((r) => r.clip_id) ?? null;
  }
  if (!clip) return null;

  const { headline, body } = splitHeadline(m.text.trim());
  return { headline, body, clip };
}

/** The composer's "CONTEXT KEPT · S03 / 2C" readout — the scene/slate the
 * most recent successful turn was actually about, read off its real tool
 * result rows. Scans backward so a clarifying turn with no rows doesn't
 * blank out context the previous turn established. Null once there is
 * nothing yet to be scoped to. */
export function sessionContext(messages: ChatMessage[]): SessionContext | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "agent") continue;
    const result = lastResult(m.toolEvents);
    const row = result?.rows.find((r) => r.scene);
    if (row?.scene) return { scene: row.scene, slate: row.slate };
  }
  return null;
}

/** The coverage-gap callout's body, generated from get_coverage's real gap
 * fields — null when the row carries none (nothing to show, never a false
 * "no gaps" claim rendered as if it were a finding). */
export function describeGap(row: ResultRow): string | null {
  const parts: string[] = [];
  if (row.no_tight_shot?.length) {
    parts.push(`No tight coverage on ${row.no_tight_shot.join(", ")}.`);
  }
  if (row.wide_coverage?.length) {
    parts.push(`Only caught in wide shots: ${row.wide_coverage.join(", ")}.`);
  }
  if (row.never_appeared?.length) {
    parts.push(`Never appears in this scene's coverage: ${row.never_appeared.join(", ")}.`);
  }
  if (row.unmatched_expected?.length) {
    parts.push(
      `Expected but not resolvable from Gemini's on-screen names: ${row.unmatched_expected.join(", ")}.`
    );
  }
  return parts.length ? parts.join(" ") : null;
}
