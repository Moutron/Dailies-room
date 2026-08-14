import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SessionView } from "./SessionView";
import { streamChat } from "../api";
import type { ChatEvent } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    streamChat: vi.fn(),
  };
});

const mockStreamChat = vi.mocked(streamChat);

async function* eventsFrom(events: ChatEvent[]) {
  for (const event of events) yield event;
}

// eslint-disable-next-line require-yield -- this generator's whole point is to throw before yielding
async function* throwingEvents(): AsyncGenerator<ChatEvent> {
  throw new Error("network down");
}

// CoverageGapCallout links to /coverage, which needs a router context.
function renderSession(onSeek = vi.fn()) {
  return render(
    <MemoryRouter>
      <SessionView onSeek={onSeek} />
    </MemoryRouter>
  );
}

function typeAndSend(text: string) {
  const input = screen.getByLabelText("Ask your footage something");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
}

describe("SessionView", () => {
  beforeEach(() => {
    mockStreamChat.mockReset();
  });

  it("shows example prompts before any message is sent", () => {
    renderSession();
    expect(screen.getByText("Ask the footage a question.")).toBeInTheDocument();
    // The composer's chips duplicate the same three prompts, so there are
    // two matches for this name — presence is what matters here.
    expect(
      screen.getAllByRole("button", { name: "What coverage do we have on the bridge scene?" })
    ).toHaveLength(2);
  });

  it("clicking an empty-state prompt populates the composer without sending", () => {
    renderSession();
    const [emptyStatePrompt] = screen.getAllByRole("button", {
      name: "What coverage do we have on the bridge scene?",
    });
    fireEvent.click(emptyStatePrompt);

    expect(screen.getByLabelText("Ask your footage something")).toHaveValue(
      "What coverage do we have on the bridge scene?"
    );
    expect(mockStreamChat).not.toHaveBeenCalled();
  });

  it("clicking a composer suggestion chip populates without sending", () => {
    renderSession();
    const [, composerChip] = screen.getAllByRole("button", { name: "Which take of 2A plays best?" });
    fireEvent.click(composerChip);

    expect(screen.getByLabelText("Ask your footage something")).toHaveValue(
      "Which take of 2A plays best?"
    );
    expect(mockStreamChat).not.toHaveBeenCalled();
  });

  it("Enter sends the typed question and renders the streamed agent reply", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "message", text: "Here is the coverage.", final: true },
        { type: "done" },
      ])
    );

    renderSession();
    typeAndSend("What coverage do we have?");

    expect(screen.getByText("What coverage do we have?")).toBeInTheDocument();
    expect(await screen.findByText("Here is the coverage.")).toBeInTheDocument();
    expect(mockStreamChat).toHaveBeenCalledWith("What coverage do we have?", expect.any(String));
  });

  it("Shift+Enter inserts a newline instead of sending", () => {
    renderSession();
    const input = screen.getByLabelText("Ask your footage something");
    fireEvent.change(input, { target: { value: "line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    expect(mockStreamChat).not.toHaveBeenCalled();
  });

  it("renders a takes table from the last tool_result event", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "tool_call", tool: "search_dialogue", args: { query: "hand" } },
        {
          type: "tool_result",
          tool: "search_dialogue",
          result: {
            result: [
              { clip_id: "c1", text: "Where were you?", timecode_in: "00:00:01:00", speaker: "MAN" },
            ],
          },
        },
        { type: "message", text: "Found it.", final: true },
        { type: "done" },
      ])
    );

    renderSession();
    typeAndSend("dialogue about the hand");

    expect(await screen.findByText('"Where were you?"')).toBeInTheDocument();
    expect(screen.getByText("AGENT · 1 LINE FOUND")).toBeInTheDocument();
  });

  it("renders a coverage-gap callout when get_coverage reports a gap", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "tool_call", tool: "get_coverage", args: { scene: "S01" } },
        {
          type: "tool_result",
          tool: "get_coverage",
          result: {
            result: [
              {
                clip_id: "c1",
                timecode_in: "00:00:01:00",
                no_tight_shot: ["MAN", "WOMAN"],
              },
            ],
          },
        },
        { type: "message", text: "No tight shots here.", final: true },
        { type: "done" },
      ])
    );

    renderSession();
    typeAndSend("coverage on S01");

    expect(await screen.findByText("COVERAGE GAP")).toBeInTheDocument();
    expect(screen.getByText("No tight coverage on MAN, WOMAN.")).toBeInTheDocument();
  });

  it("renders the evidence row from tool_evidence events", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "tool_call", tool: "search_dialogue", args: {} },
        { type: "tool_result", tool: "search_dialogue", result: { result: [] } },
        {
          type: "tool_evidence",
          tool: "search_dialogue",
          queries: [{ table: "dialogue", sql: "SELECT 1", elapsed_ms: 240, row_count: 0 }],
        },
        { type: "message", text: "Nothing found.", final: true },
        { type: "done" },
      ])
    );

    renderSession();
    typeAndSend("anything");

    const evidenceLabel = await screen.findByText("EVIDENCE");
    const summary = evidenceLabel.closest("summary");
    expect(summary?.textContent).toContain("dialogue · 0 rows");
    expect(screen.getByText("0.24s")).toBeInTheDocument();
  });

  it("shows a muted rate-limit notice, not an error, on rate_limited", async () => {
    mockStreamChat.mockReturnValue(eventsFrom([{ type: "rate_limited", retryAfterSeconds: 3 }]));

    renderSession();
    typeAndSend("one more question");

    expect(await screen.findByText("Too many requests — try again in 3s.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a connection-lost message when the stream throws", async () => {
    mockStreamChat.mockImplementation(throwingEvents);

    renderSession();
    typeAndSend("which take plays best");

    expect(
      await screen.findByText("Lost connection to the agent. Check your connection and try again.")
    ).toBeInTheDocument();
  });

  it("ignores empty submissions", () => {
    renderSession();
    fireEvent.keyDown(screen.getByLabelText("Ask your footage something"), { key: "Enter" });
    expect(mockStreamChat).not.toHaveBeenCalled();
  });

  it("disables the input while a request is in flight", async () => {
    let resolveEvents!: () => void;
    const pending = new Promise<void>((resolve) => {
      resolveEvents = resolve;
    });
    mockStreamChat.mockImplementation(async function* () {
      await pending;
      yield { type: "done" } as ChatEvent;
    });

    renderSession();
    typeAndSend("show me every close-up we shot");

    expect(screen.getByLabelText("Ask your footage something")).toBeDisabled();
    resolveEvents();
    await waitFor(() =>
      expect(screen.getByLabelText("Ask your footage something")).not.toBeDisabled()
    );
  });

  it("renders the no-dialogue honesty card when dialogue evidence is real zero rows", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "tool_call", tool: "search_visuals", args: { scene: "S03" } },
        {
          type: "tool_result",
          tool: "search_visuals",
          result: {
            result: [
              {
                clip_id: "03_2c_take",
                timecode_in: "00:41:09:14",
                shot_type: "medium_close",
                duration_s: 5,
              },
            ],
          },
        },
        {
          type: "tool_evidence",
          tool: "search_dialogue",
          queries: [{ table: "dialogue", sql: "SELECT 1", elapsed_ms: 240, row_count: 0 }],
        },
        {
          type: "message",
          text: "Scene 03 is a visual effects plate. Nothing was transcribed, so there is nothing to quote.",
          final: true,
        },
        { type: "done" },
      ])
    );

    renderSession();
    typeAndSend("What dialogue is in scene S03 take 3?");

    expect(await screen.findByText("NO DIALOGUE IN THIS TAKE")).toBeInTheDocument();
    expect(screen.getByText("Scene 03 is a visual effects plate.")).toBeInTheDocument();
    expect(
      screen.getByText("Nothing was transcribed, so there is nothing to quote.")
    ).toBeInTheDocument();
    expect(screen.getByText("AGENT · 03_2c_take")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play 03_2c_take" })).toBeInTheDocument();
  });

  it("renders the clarifying-question card with real slate options, never a fixed three", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "tool_call", tool: "get_coverage", args: { scene: "S03" } },
        {
          type: "tool_result",
          tool: "get_coverage",
          result: {
            result: [
              { clip_id: "a", scene: "S03", slate: "2A", take: 1, reel: "A003", timecode_in: "00:41:09:14" },
              { clip_id: "b", scene: "S03", slate: "2C", take: 3, reel: "A003", timecode_in: "00:52:44:02" },
              { clip_id: "c", scene: "S03", slate: "2E", take: 5, reel: "A005", timecode_in: "01:18:02:10" },
            ],
          },
        },
        { type: "message", text: "Scene S03 has three slates. Which one did you mean?", final: true },
        { type: "done" },
      ])
    );

    renderSession();
    typeAndSend("Dialogue in scene S03 take 3");

    expect(await screen.findByText("AGENT NEEDS ONE THING")).toBeInTheDocument();
    expect(screen.getByText("Scene S03 has three slates. Which one did you mean?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2A · T1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2C · T3/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2E · T5/ })).toBeInTheDocument();
    // The false "take numbers repeat across slates" claim must never ship —
    // this scene's takes (1, 3, 5) are all distinct, so no reason line.
    expect(screen.queryByText(/take numbers repeat/i)).not.toBeInTheDocument();
  });

  it("sends the clicked clarifying option as the next turn", async () => {
    mockStreamChat.mockReturnValueOnce(
      eventsFrom([
        { type: "tool_call", tool: "get_coverage", args: { scene: "S03" } },
        {
          type: "tool_result",
          tool: "get_coverage",
          result: {
            result: [
              { clip_id: "a", scene: "S03", slate: "2A", take: 1 },
              { clip_id: "b", scene: "S03", slate: "2C", take: 3 },
            ],
          },
        },
        { type: "message", text: "Which slate did you mean?", final: true },
        { type: "done" },
      ])
    );
    mockStreamChat.mockReturnValueOnce(
      eventsFrom([{ type: "message", text: "Here you go.", final: true }, { type: "done" }])
    );

    renderSession();
    typeAndSend("Dialogue in scene S03 take 3");
    await screen.findByText("Which slate did you mean?");

    fireEvent.click(screen.getByRole("button", { name: /2C · T3/ }));

    expect(await screen.findByText("Slate 2C, take 3")).toBeInTheDocument();
    expect(mockStreamChat).toHaveBeenLastCalledWith("Slate 2C, take 3", expect.any(String));
  });

  it("shows the pending pulse with a substage label driven by the tool call", async () => {
    let resolveEvents!: () => void;
    const pending = new Promise<void>((resolve) => {
      resolveEvents = resolve;
    });
    mockStreamChat.mockImplementation(async function* () {
      yield { type: "tool_call", tool: "get_coverage", args: {} };
      await pending;
      yield { type: "done" } as ChatEvent;
    });

    renderSession();
    typeAndSend("coverage please");

    expect(await screen.findByText("reading coverage…")).toBeInTheDocument();
    resolveEvents();
  });
});
