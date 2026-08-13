import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolTrace } from "./ToolTrace";
import type { ToolEvent } from "../types";

describe("ToolTrace", () => {
  it("renders nothing when there are no events", () => {
    const { container } = render(<ToolTrace events={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("summarizes a search_dialogue call paired with its result", () => {
    const events: ToolEvent[] = [
      { kind: "call", tool: "search_dialogue", args: { query: "hand", scene: "S03" } },
      {
        kind: "result",
        tool: "search_dialogue",
        rows: [{ clip_id: "c1", scene: "S03" }],
        isError: false,
      },
    ];
    render(<ToolTrace events={events} />);

    expect(screen.getByText("1 search of the footage")).toBeInTheDocument();
    expect(
      screen.getByText('Searched dialogue for "hand" (in S03), found 1 match.')
    ).toBeInTheDocument();
  });

  it("describes an error result", () => {
    const events: ToolEvent[] = [
      { kind: "call", tool: "get_coverage", args: {} },
      { kind: "result", tool: "get_coverage", rows: [{ error: "down" }], isError: true },
    ];
    render(<ToolTrace events={events} />);

    expect(
      screen.getByText("Pulled coverage for every scene, the footage index was unreachable.")
    ).toBeInTheDocument();
  });

  it("describes an embedding_mismatch error result distinctly from unreachable", () => {
    const events: ToolEvent[] = [
      { kind: "call", tool: "get_coverage", args: {} },
      {
        kind: "result",
        tool: "get_coverage",
        rows: [{ error: "bad dims", error_type: "embedding_mismatch" }],
        isError: true,
      },
    ];
    render(<ToolTrace events={events} />);

    expect(
      screen.getByText("Pulled coverage for every scene, the search index is misconfigured.")
    ).toBeInTheDocument();
  });

  it("pluralizes the summary count for multiple calls", () => {
    const events: ToolEvent[] = [
      { kind: "call", tool: "get_coverage", args: {} },
      { kind: "result", tool: "get_coverage", rows: [], isError: false },
      { kind: "call", tool: "search_visuals", args: { query: "wide shot" } },
      { kind: "result", tool: "search_visuals", rows: [], isError: false },
    ];
    render(<ToolTrace events={events} />);

    expect(screen.getByText("2 searches of the footage")).toBeInTheDocument();
  });
});
