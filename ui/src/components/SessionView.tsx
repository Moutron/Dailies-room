import { useEffect, useRef, useState } from "react";
import { rowsFromToolResult, streamChat } from "../api";
import {
  DEMO_PROMPTS,
  detectClarifyingQuestion,
  detectNoDialogueAnswer,
  lastResult,
  resultCountLabel,
  sessionContext,
  substageLabel,
} from "../agentCopy";
import { renderAgentText } from "../markdown";
import type { ChatMessage, SessionTurn, ToolEvent } from "../types";
import { ClarifyingCard } from "./ClarifyingCard";
import { Composer } from "./Composer";
import { CoverageGapCallout } from "./CoverageGapCallout";
import { EvidenceRow } from "./EvidenceRow";
import { NoDialogueCard, NoDialogueClipStrip } from "./NoDialogueCard";
import { RateLimitNotice } from "./RateLimitNotice";
import { TakesTable } from "./TakesTable";

function newId(): string {
  return crypto.randomUUID();
}

export function SessionView({
  onSeek,
  activeReel,
  onSessionChange,
  circledClipIds,
}: {
  onSeek: (clipId: string, seconds: number) => void;
  activeReel?: string;
  /** Reports the real turn list up to AskPage so it can pass it to the
   * rail's "This session" list — SessionView owns the conversation state,
   * the shell owns the rail, so this is how the real data crosses that
   * boundary rather than each side keeping its own copy. */
  onSessionChange?: (turns: SessionTurn[]) => void;
  /** Real clip_ids currently circled — passed down to TakesTable so a
   * row only highlights when it's actually flagged. */
  circledClipIds?: Set<string>;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionResetNotice, setSessionResetNotice] = useState(false);
  const sessionId = useRef(newId());
  const sentTurnCount = useRef(0);

  useEffect(() => {
    if (!onSessionChange) return;
    const userMsgs = messages.filter((m) => m.role === "user");
    onSessionChange(
      userMsgs.map((m, i) => ({ id: m.id, text: m.text, active: i === userMsgs.length - 1 }))
    );
  }, [messages, onSessionChange]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    setInput("");

    const userMsg: ChatMessage = {
      id: newId(),
      role: "user",
      text: question,
      toolEvents: [],
      evidence: [],
      streaming: false,
    };
    const agentId = newId();
    const agentMsg: ChatMessage = {
      id: agentId,
      role: "agent",
      text: "",
      toolEvents: [],
      evidence: [],
      streaming: true,
    };
    setMessages((m) => [...m, userMsg, agentMsg]);
    sentTurnCount.current += 1;

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
        } else if (event.type === "tool_evidence") {
          patch((m) => ({ ...m, evidence: [...m.evidence, ...event.queries] }));
        } else if (event.type === "message") {
          const t = event.text;
          patch((m) => ({ ...m, text: t }));
        } else if (event.type === "error") {
          patch((m) => ({ ...m, errorText: event.message, streaming: false }));
        } else if (event.type === "rate_limited") {
          const seconds = event.retryAfterSeconds;
          patch((m) => ({ ...m, rateLimitedSeconds: seconds, streaming: false }));
        } else if (event.type === "done") {
          patch((m) => ({ ...m, streaming: false }));
          // Session affinity can route a later request to a Cloud Run
          // instance that never saw this session_id before, silently
          // starting a fresh one under the same id. The server's real
          // turn_count then comes back lower than what we've actually
          // sent — that mismatch is the only honest signal we have.
          if (event.turn_count != null && event.turn_count < sentTurnCount.current) {
            setSessionResetNotice(true);
          }
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

  const context = sessionContext(messages);

  return (
    <div className="session-view">
      <div className="session-view__log" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty-state">
            <p className="empty-state__lead">Ask the footage a question.</p>
            <p>Try:</p>
            <ul>
              {DEMO_PROMPTS.map((p) => (
                <li key={p}>
                  <button type="button" className="empty-state__prompt" onClick={() => setInput(p)}>
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {messages.map((m, i) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="message message--user">
                <div className="message__meta mono">YOU</div>
                <div className="message__bubble">{m.text}</div>
              </div>
            );
          }

          if (m.rateLimitedSeconds != null) {
            return (
              <div key={m.id} className="message message--agent">
                <RateLimitNotice retryAfterSeconds={m.rateLimitedSeconds} />
              </div>
            );
          }

          if (m.streaming && !m.text) {
            return (
              <div key={m.id} className="message message--agent">
                <div className="agent-header agent-header--pending">
                  <span className="agent-header__chip agent-header__chip--pulsing mono" aria-hidden="true">
                    DR
                  </span>
                  <span className="agent-header__label mono">{substageLabel(m.toolEvents)}</span>
                </div>
              </div>
            );
          }

          const clarifying = m.text ? detectClarifyingQuestion(m) : null;
          if (clarifying) {
            return (
              <div key={m.id} className="message message--agent">
                <div className="agent-header">
                  <span className="agent-header__chip mono" aria-hidden="true">
                    DR
                  </span>
                  <span className="agent-header__label agent-header__label--needs-input mono">
                    AGENT NEEDS ONE THING
                  </span>
                </div>
                <ClarifyingCard clarifying={clarifying} onAnswer={send} />
              </div>
            );
          }

          const noDialogue = m.text ? detectNoDialogueAnswer(m, messages[i - 1]?.text) : null;
          if (noDialogue) {
            return (
              <div key={m.id} className="message message--agent">
                <div className="agent-header">
                  <span className="agent-header__chip mono" aria-hidden="true">
                    DR
                  </span>
                  <span className="agent-header__label mono">AGENT · {noDialogue.clip?.clip_id}</span>
                </div>
                <NoDialogueCard answer={noDialogue} />
                <NoDialogueClipStrip clip={noDialogue.clip} onSeek={onSeek} />
                <EvidenceRow evidence={m.evidence} />
              </div>
            );
          }

          return (
            <div key={m.id} className="message message--agent">
              <div className="agent-header">
                <span className="agent-header__chip mono" aria-hidden="true">
                  DR
                </span>
                <span className="agent-header__label mono">
                  AGENT{resultCountLabel(m.toolEvents) ? ` · ${resultCountLabel(m.toolEvents)}` : ""}
                </span>
              </div>
              {m.text && <div className="message__text">{renderAgentText(m.text)}</div>}
              {m.errorText && (
                <p className="message__error" role="alert">
                  {m.errorText}
                </p>
              )}
              {(() => {
                const result = lastResult(m.toolEvents);
                if (!result) return null;
                return (
                  <>
                    <TakesTable tool={result.tool} rows={result.rows} onSeek={onSeek} circledClipIds={circledClipIds} />
                    {result.tool === "get_coverage" && result.rows[0] && (
                      <CoverageGapCallout row={result.rows[0]} />
                    )}
                  </>
                );
              })()}
              <EvidenceRow evidence={m.evidence} />
            </div>
          );
        })}

        {sessionResetNotice && (
          <div className="rate-limit-notice" role="status">
            Session continuity may have reset — the server started a fresh session under this id.
            Earlier context may no longer carry forward.
          </div>
        )}
      </div>

      <Composer
        value={input}
        onChange={setInput}
        onSend={() => send(input)}
        busy={busy}
        activeReel={activeReel}
        sessionContext={context}
      />
    </div>
  );
}
