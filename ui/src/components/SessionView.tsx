import { useRef, useState } from "react";
import { rowsFromToolResult, streamChat } from "../api";
import { renderAgentText } from "../markdown";
import type { ChatMessage, ToolEvent } from "../types";
import { ResultCard } from "./ResultCard";
import { ToolTrace } from "./ToolTrace";

const EXAMPLE_PROMPTS = [
  "What coverage do we have on the bridge scene?",
  "Which take of 2A plays best?",
  "Show me every close-up we shot.",
];

function newId(): string {
  return crypto.randomUUID();
}

export function SessionView({
  onSeek,
}: {
  onSeek: (clipId: string, seconds: number) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionId = useRef(newId());

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    setInput("");

    const userMsg: ChatMessage = { id: newId(), role: "user", text: question, toolEvents: [], streaming: false };
    const agentId = newId();
    const agentMsg: ChatMessage = { id: agentId, role: "agent", text: "", toolEvents: [], streaming: true };
    setMessages((m) => [...m, userMsg, agentMsg]);

    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((all) => all.map((m) => (m.id === agentId ? fn(m) : m)));

    try {
      for await (const event of streamChat(question, sessionId.current)) {
        if (event.type === "tool_call") {
          const e: ToolEvent = { kind: "call", tool: event.tool, args: event.args };
          patch((m) => ({ ...m, toolEvents: [...m.toolEvents, e] }));
        } else if (event.type === "tool_result") {
          const { rows, isError } = rowsFromToolResult(event.result);
          const e: ToolEvent = { kind: "result", tool: event.tool, rows, isError };
          patch((m) => ({ ...m, toolEvents: [...m.toolEvents, e] }));
        } else if (event.type === "message") {
          const t = event.text;
          patch((m) => ({ ...m, text: t }));
        } else if (event.type === "error") {
          patch((m) => ({ ...m, errorText: event.message, streaming: false }));
        } else if (event.type === "done") {
          patch((m) => ({ ...m, streaming: false }));
        }
      }
    } catch {
      patch((m) => ({
        ...m,
        streaming: false,
        errorText: "Lost connection to the agent. Check your connection and try again.",
      }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="session-view">
      <div className="session-view__log" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty-state">
            <p className="empty-state__lead">Ask the footage a question.</p>
            <p>Try:</p>
            <ul>
              {EXAMPLE_PROMPTS.map((p) => (
                <li key={p}>
                  <button type="button" className="empty-state__prompt" onClick={() => send(p)}>
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="message message--user">
              {m.text}
            </div>
          ) : (
            <div key={m.id} className="message message--agent">
              {m.text && <div className="message__text">{renderAgentText(m.text)}</div>}
              {m.streaming && !m.text && <p className="message__thinking">Searching the footage…</p>}
              {m.errorText && (
                <p className="message__error" role="alert">
                  {m.errorText}
                </p>
              )}
              <ToolTrace events={m.toolEvents} />
              <div className="result-grid">
                {m.toolEvents
                  .filter((e): e is Extract<ToolEvent, { kind: "result" }> => e.kind === "result" && !e.isError)
                  .flatMap((e) => e.rows)
                  .map((row, i) => (
                    <ResultCard key={i} row={row} onSeek={onSeek} />
                  ))}
              </div>
            </div>
          )
        )}
      </div>

      <form
        className="session-view__input"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <label htmlFor="question" className="sr-only">
          Ask the footage a question
        </label>
        <input
          id="question"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the footage a question…"
          disabled={busy}
          autoComplete="off"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "Asking…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
