import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SessionView } from "./SessionView";
import { streamChat } from "../api";
import type { ChatEvent } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    streamChat: vi.fn(),
    getThumbnails: vi.fn().mockResolvedValue([]),
    getClipUrl: vi.fn().mockResolvedValue("https://signed.example/clip.mp4"),
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

describe("SessionView", () => {
  beforeEach(() => {
    mockStreamChat.mockReset();
  });

  it("shows example prompts before any message is sent", () => {
    render(<SessionView onSeek={vi.fn()} />);
    expect(screen.getByText("Ask the footage a question.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "What coverage do we have on the bridge scene?" })
    ).toBeInTheDocument();
  });

  it("sends the typed question and renders the streamed agent reply", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "message", text: "Here is the coverage.", final: true },
        { type: "done" },
      ])
    );

    render(<SessionView onSeek={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Ask the footage a question"), {
      target: { value: "What coverage do we have?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(screen.getByText("What coverage do we have?")).toBeInTheDocument();
    expect(await screen.findByText("Here is the coverage.")).toBeInTheDocument();
    expect(mockStreamChat).toHaveBeenCalledWith(
      "What coverage do we have?",
      expect.any(String)
    );
  });

  it("renders result cards from a tool_result event", async () => {
    mockStreamChat.mockReturnValue(
      eventsFrom([
        { type: "tool_call", tool: "search_dialogue", args: { query: "hand" } },
        {
          type: "tool_result",
          tool: "search_dialogue",
          result: { result: [{ clip_id: "c1", text: "Where were you?" }] },
        },
        { type: "message", text: "Found it.", final: true },
        { type: "done" },
      ])
    );

    render(<SessionView onSeek={vi.fn()} />);
    fireEvent.click(
      screen.getByRole("button", { name: "What coverage do we have on the bridge scene?" })
    );

    expect(await screen.findByText('"Where were you?"')).toBeInTheDocument();
  });

  it("shows a connection-lost message when the stream throws", async () => {
    mockStreamChat.mockImplementation(throwingEvents);

    render(<SessionView onSeek={vi.fn()} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Which take of 2A plays best?" })
    );

    expect(
      await screen.findByText("Lost connection to the agent. Check your connection and try again.")
    ).toBeInTheDocument();
  });

  it("ignores empty submissions", () => {
    render(<SessionView onSeek={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
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

    render(<SessionView onSeek={vi.fn()} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Show me every close-up we shot." })
    );

    expect(screen.getByLabelText("Ask the footage a question")).toBeDisabled();
    resolveEvents();
    await waitFor(() =>
      expect(screen.getByLabelText("Ask the footage a question")).not.toBeDisabled()
    );
  });
});
