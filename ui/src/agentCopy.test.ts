import { describe, expect, it } from "vitest";
import {
  describeGap,
  detectClarifyingQuestion,
  detectNoDialogueAnswer,
  formatDuration,
  lastResult,
  resultCountLabel,
  sessionContext,
  shotTypeLabel,
  substageLabel,
} from "./agentCopy";
import type { ChatMessage, ToolEvent } from "./types";

function agentMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    role: "agent",
    text: "",
    toolEvents: [],
    evidence: [],
    streaming: false,
    ...overrides,
  };
}

describe("shotTypeLabel", () => {
  it("maps known enum values to short labels", () => {
    expect(shotTypeLabel("extreme_wide")).toBe("WIDE");
    expect(shotTypeLabel("wide")).toBe("WIDE");
    expect(shotTypeLabel("medium")).toBe("MED");
    expect(shotTypeLabel("medium_close")).toBe("MCU");
    expect(shotTypeLabel("close")).toBe("CU");
    expect(shotTypeLabel("extreme_close")).toBe("CU");
    expect(shotTypeLabel("insert")).toBe("INSERT");
  });

  it("falls back to an em dash when absent", () => {
    expect(shotTypeLabel(undefined)).toBe("—");
  });

  it("falls back to the raw value uppercased for an unmapped enum value", () => {
    expect(shotTypeLabel("unknown")).toBe("UNKNOWN");
  });
});

describe("formatDuration", () => {
  it("formats seconds as m:ss", () => {
    expect(formatDuration(115)).toBe("1:55");
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(65)).toBe("1:05");
  });

  it("falls back to an em dash when missing", () => {
    expect(formatDuration(undefined)).toBe("—");
  });
});

describe("lastResult", () => {
  it("returns null when there are no result events", () => {
    expect(lastResult([{ kind: "call", tool: "search_dialogue", args: {} }])).toBeNull();
  });

  it("skips error results", () => {
    const events: ToolEvent[] = [
      { kind: "result", tool: "search_dialogue", rows: [{ error: "x" }], isError: true },
    ];
    expect(lastResult(events)).toBeNull();
  });

  it("returns the last non-error result", () => {
    const events: ToolEvent[] = [
      { kind: "result", tool: "search_visuals", rows: [{ clip_id: "a" }], isError: false },
      { kind: "result", tool: "get_coverage", rows: [{ clip_id: "b" }, { clip_id: "c" }], isError: false },
    ];
    const result = lastResult(events);
    expect(result?.tool).toBe("get_coverage");
    expect(result?.rows).toHaveLength(2);
  });
});

describe("resultCountLabel", () => {
  it("returns null with no results", () => {
    expect(resultCountLabel([])).toBeNull();
  });

  it("picks the noun for the tool and pluralizes", () => {
    const events: ToolEvent[] = [
      { kind: "result", tool: "get_coverage", rows: [{ clip_id: "a" }, { clip_id: "b" }, { clip_id: "c" }], isError: false },
    ];
    expect(resultCountLabel(events)).toBe("3 TAKES FOUND");
  });

  it("does not pluralize a single result", () => {
    const events: ToolEvent[] = [
      { kind: "result", tool: "search_dialogue", rows: [{ clip_id: "a" }], isError: false },
    ];
    expect(resultCountLabel(events)).toBe("1 LINE FOUND");
  });

  it("reports zero results honestly", () => {
    const events: ToolEvent[] = [
      { kind: "result", tool: "search_visuals", rows: [], isError: false },
    ];
    expect(resultCountLabel(events)).toBe("NOTHING FOUND");
  });
});

describe("substageLabel", () => {
  it("defaults to a generic label with no tool calls yet", () => {
    expect(substageLabel([])).toBe("searching the footage…");
  });

  it("maps each tool to its gerund phrase", () => {
    expect(substageLabel([{ kind: "call", tool: "get_coverage", args: {} }])).toBe(
      "reading coverage…"
    );
    expect(substageLabel([{ kind: "call", tool: "compare_takes", args: {} }])).toBe(
      "comparing takes…"
    );
  });

  it("uses the most recent call", () => {
    const events: ToolEvent[] = [
      { kind: "call", tool: "search_visuals", args: {} },
      { kind: "result", tool: "search_visuals", rows: [], isError: false },
      { kind: "call", tool: "get_coverage", args: {} },
    ];
    expect(substageLabel(events)).toBe("reading coverage…");
  });
});

describe("detectClarifyingQuestion", () => {
  it("returns null when the answer isn't phrased as a question", () => {
    const m = agentMessage({
      text: "Slate 2C, take 3 has the dialogue you want.",
      toolEvents: [
        {
          kind: "result",
          tool: "get_coverage",
          isError: false,
          rows: [
            { clip_id: "a", scene: "S03", slate: "2A", take: 1 },
            { clip_id: "b", scene: "S03", slate: "2C", take: 3 },
          ],
        },
      ],
    });
    expect(detectClarifyingQuestion(m)).toBeNull();
  });

  it("returns null with fewer than two distinct slate/take candidates", () => {
    const m = agentMessage({
      text: "Which take did you mean?",
      toolEvents: [
        { kind: "result", tool: "get_coverage", isError: false, rows: [{ clip_id: "a", scene: "S03", slate: "2C", take: 3 }] },
      ],
    });
    expect(detectClarifyingQuestion(m)).toBeNull();
  });

  it("builds real options from the tool result rows, deduped by slate/take", () => {
    const m = agentMessage({
      text: "Scene S03 has three slates. Which one did you mean?",
      toolEvents: [
        {
          kind: "result",
          tool: "get_coverage",
          isError: false,
          rows: [
            { clip_id: "a", scene: "S03", slate: "2A", take: 1, reel: "A003", timecode_in: "00:41:09:14" },
            { clip_id: "b", scene: "S03", slate: "2C", take: 3, reel: "A003", timecode_in: "00:52:44:02" },
            { clip_id: "c", scene: "S03", slate: "2E", take: 5, reel: "A005", timecode_in: "01:18:02:10" },
          ],
        },
      ],
    });
    const clarifying = detectClarifyingQuestion(m);
    expect(clarifying?.options).toEqual([
      { clip_id: "a", slate: "2A", take: 1, reel: "A003", timecodeShort: "00:41:09" },
      { clip_id: "b", slate: "2C", take: 3, reel: "A003", timecodeShort: "00:52:44" },
      { clip_id: "c", slate: "2E", take: 5, reel: "A005", timecodeShort: "01:18:02" },
    ]);
  });

  it("omits the reason line when no take number actually repeats", () => {
    const m = agentMessage({
      text: "Which slate did you mean?",
      toolEvents: [
        {
          kind: "result",
          tool: "get_coverage",
          isError: false,
          rows: [
            { clip_id: "a", scene: "S03", slate: "2A", take: 1 },
            { clip_id: "b", scene: "S03", slate: "2C", take: 3 },
          ],
        },
      ],
    });
    expect(detectClarifyingQuestion(m)?.reason).toBeNull();
  });

  it("generates a real reason only when a take number genuinely repeats across slates", () => {
    const m = agentMessage({
      text: "Which slate did you mean?",
      toolEvents: [
        {
          kind: "result",
          tool: "get_coverage",
          isError: false,
          rows: [
            { clip_id: "a", scene: "S01", slate: "1A", take: 1 },
            { clip_id: "b", scene: "S01", slate: "1B", take: 1 },
          ],
        },
      ],
    });
    expect(detectClarifyingQuestion(m)?.reason).toBe(
      "Scene S01 has more than one take 1 across different slates."
    );
  });
});

describe("detectNoDialogueAnswer", () => {
  it("returns null without a zero-row dialogue evidence entry", () => {
    const m = agentMessage({
      text: "There is dialogue here.",
      evidence: [{ table: "dialogue", sql: "x", elapsed_ms: 1, row_count: 2 }],
      toolEvents: [{ kind: "result", tool: "search_visuals", isError: false, rows: [{ clip_id: "a" }] }],
    });
    expect(detectNoDialogueAnswer(m)).toBeNull();
  });

  it("returns null when no clip is resolvable from this turn's rows", () => {
    const m = agentMessage({
      text: "Nothing found.",
      evidence: [{ table: "dialogue", sql: "x", elapsed_ms: 1, row_count: 0 }],
    });
    expect(detectNoDialogueAnswer(m)).toBeNull();
  });

  it("splits the agent's real text into a headline and substitute body", () => {
    const m = agentMessage({
      text: "Scene 03 is a visual effects plate. Nothing was transcribed, so there is nothing to quote.",
      evidence: [{ table: "dialogue", sql: "x", elapsed_ms: 1, row_count: 0 }],
      toolEvents: [
        { kind: "result", tool: "search_visuals", isError: false, rows: [{ clip_id: "03_2c_take", shot_type: "medium" }] },
      ],
    });
    const answer = detectNoDialogueAnswer(m);
    expect(answer?.headline).toBe("Scene 03 is a visual effects plate.");
    expect(answer?.body).toBe("Nothing was transcribed, so there is nothing to quote.");
    expect(answer?.clip?.clip_id).toBe("03_2c_take");
  });

  it("detects compare_takes' shape — rows carrying their own empty dialogue array", () => {
    const m = agentMessage({
      text: "There is no dialogue in Reel A003, 01:42:00:00 (S03, Slate 2C, Take 3).",
      toolEvents: [
        {
          kind: "result",
          tool: "compare_takes",
          isError: false,
          rows: [
            { clip_id: "03_2a_take", scene: "S03", slate: "2A", take: 1, dialogue: [] },
            { clip_id: "03_2c_take", scene: "S03", slate: "2C", take: 3, dialogue: [] },
            { clip_id: "03_2e_take", scene: "S03", slate: "2E", take: 5, dialogue: [] },
          ],
        },
      ],
    });
    const answer = detectNoDialogueAnswer(m, "What dialogue is in scene S03 take 3?");
    expect(answer?.clip?.clip_id).toBe("03_2c_take");
  });

  it("falls back to the first empty-dialogue row when no take number is stated", () => {
    const m = agentMessage({
      text: "None of these takes have dialogue.",
      toolEvents: [
        {
          kind: "result",
          tool: "compare_takes",
          isError: false,
          rows: [
            { clip_id: "03_2a_take", scene: "S03", slate: "2A", take: 1, dialogue: [] },
            { clip_id: "03_2c_take", scene: "S03", slate: "2C", take: 3, dialogue: [] },
          ],
        },
      ],
    });
    expect(detectNoDialogueAnswer(m)?.clip?.clip_id).toBe("03_2a_take");
  });

  it("does not treat a take with real dialogue lines as a no-dialogue answer", () => {
    const m = agentMessage({
      text: "Take 1 has one line of dialogue.",
      toolEvents: [
        {
          kind: "result",
          tool: "compare_takes",
          isError: false,
          rows: [{ clip_id: "01_1a_take", scene: "S01", slate: "1A", take: 1, dialogue: [{ text: "hi" }] }],
        },
      ],
    });
    expect(detectNoDialogueAnswer(m)).toBeNull();
  });
});

describe("sessionContext", () => {
  it("returns null before any turn has resolved a scene", () => {
    expect(sessionContext([])).toBeNull();
  });

  it("reads the scene/slate off the most recent agent turn with rows", () => {
    const messages: ChatMessage[] = [
      agentMessage({
        toolEvents: [
          { kind: "result", tool: "get_coverage", isError: false, rows: [{ clip_id: "a", scene: "S03", slate: "2C" }] },
        ],
      }),
    ];
    expect(sessionContext(messages)).toEqual({ scene: "S03", slate: "2C" });
  });

  it("keeps the earlier context when a later turn has no result rows", () => {
    const messages: ChatMessage[] = [
      agentMessage({
        id: "m1",
        toolEvents: [
          { kind: "result", tool: "get_coverage", isError: false, rows: [{ clip_id: "a", scene: "S03", slate: "2C" }] },
        ],
      }),
      agentMessage({ id: "m2", text: "Which slate did you mean?" }),
    ];
    expect(sessionContext(messages)).toEqual({ scene: "S03", slate: "2C" });
  });
});

describe("describeGap", () => {
  it("returns null when no gap fields are set", () => {
    expect(describeGap({})).toBeNull();
  });

  it("describes no_tight_shot", () => {
    expect(describeGap({ no_tight_shot: ["MAN", "WOMAN"] })).toBe(
      "No tight coverage on MAN, WOMAN."
    );
  });

  it("combines multiple gap kinds", () => {
    const body = describeGap({
      no_tight_shot: ["MAN"],
      wide_coverage: ["WOMAN"],
      never_appeared: ["MARCO"],
      unmatched_expected: ["THOM"],
    });
    expect(body).toBe(
      "No tight coverage on MAN. Only caught in wide shots: WOMAN. " +
        "Never appears in this scene's coverage: MARCO. " +
        "Expected but not resolvable from Gemini's on-screen names: THOM."
    );
  });
});
