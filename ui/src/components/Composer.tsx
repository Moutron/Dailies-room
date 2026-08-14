import type { KeyboardEvent } from "react";
import { DEMO_PROMPTS } from "../agentCopy";
import type { SessionContext } from "../types";

export function Composer({
  value,
  onChange,
  onSend,
  busy,
  activeReel,
  sessionContext,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  busy: boolean;
  /** The loaded clip's reel, when one is loaded — the composer's scope
   * readout only renders when there's a real value to show. */
  activeReel?: string;
  /** The conversation's real scene/slate context, once a turn has resolved
   * one — takes over the scope readout from activeReel, since it's the
   * more relevant "what will a follow-up be scoped to" signal. */
  sessionContext?: SessionContext | null;
}) {
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="composer">
      <div className="composer__chips">
        {DEMO_PROMPTS.map((s) => (
          <button type="button" key={s} className="composer__chip" onClick={() => onChange(s)}>
            {s}
          </button>
        ))}
      </div>
      <form
        className="composer__row"
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
      >
        <span className="composer__prefix mono" aria-hidden="true">
          ›
        </span>
        <label htmlFor="question" className="sr-only">
          Ask your footage something
        </label>
        <textarea
          id="question"
          className="composer__input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask your footage something…"
          disabled={busy}
          rows={1}
        />
        {sessionContext ? (
          <span className="composer__scope mono">
            CONTEXT KEPT · {sessionContext.scene}
            {sessionContext.slate ? ` / ${sessionContext.slate}` : ""}
          </span>
        ) : (
          activeReel && (
            <span className="composer__scope mono">
              {activeReel}
            </span>
          )
        )}
        <button type="submit" className="composer__send" disabled={busy || !value.trim()} aria-label="Ask">
          ↵
        </button>
      </form>
    </div>
  );
}
