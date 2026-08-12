import type { ToolCallEvent, ToolEvent, ToolResultEvent } from "../types";

function describeCall(call: ToolCallEvent): string {
  const a = call.args as Record<string, unknown>;
  switch (call.tool) {
    case "search_dialogue": {
      const filters = [a.scene && `in ${a.scene}`, a.speaker && `spoken by ${a.speaker}`]
        .filter(Boolean)
        .join(", ");
      return `Searched dialogue for "${a.query}"${filters ? ` (${filters})` : ""}`;
    }
    case "search_visuals": {
      const filters = a.shot_type ? ` (${a.shot_type} shots)` : "";
      return `Searched visuals for "${a.query}"${filters}`;
    }
    case "get_coverage":
      return a.scene ? `Pulled coverage for ${a.scene}` : "Pulled coverage for every scene";
    case "compare_takes": {
      const where = [a.slate ? `slate ${a.slate}` : null, a.scene].filter(Boolean).join(", ");
      return a.query ? `Compared takes of "${a.query}" in ${where}` : `Compared every take in ${where}`;
    }
    default:
      return `Called ${call.tool}`;
  }
}

function describeResult(result: ToolResultEvent): string {
  if (result.isError) return "the footage index was unreachable";
  const n = result.rows.length;
  if (n === 0) return "found nothing";
  const scenes = new Set(result.rows.map((r) => r.scene).filter(Boolean));
  const across = scenes.size > 1 ? ` across ${scenes.size} scenes` : "";
  return `found ${n} match${n === 1 ? "" : "es"}${across}`;
}

/** Collapsed by default — proof the answer came from the footage, not
 * debug output. Pairs each tool_call with the tool_result that follows it. */
export function ToolTrace({ events }: { events: ToolEvent[] }) {
  if (events.length === 0) return null;

  const lines: string[] = [];
  for (let i = 0; i < events.length; i++) {
    const event = events[i];
    if (event.kind !== "call") continue;
    const next = events[i + 1];
    const resultText = next?.kind === "result" ? `, ${describeResult(next)}.` : "…";
    lines.push(`${describeCall(event)}${resultText}`);
  }

  return (
    <details className="tool-trace">
      <summary>
        {lines.length} search{lines.length === 1 ? "" : "es"} of the footage
      </summary>
      <ul>
        {lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </details>
  );
}
