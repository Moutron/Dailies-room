import type { ClarifyingQuestion } from "../agentCopy";

/** Screen #1b's clarifying-question card. Renders only when SessionView's
 * detectClarifyingQuestion found a genuine turn to render — options are the
 * real candidate rows the agent's own tool call returned, not a fixed list
 * of three, and the reason line is generated from real repeated takes (or
 * omitted, never the mockup's blanket claim). Clicking an option sends it
 * as the next turn, same session. */
export function ClarifyingCard({
  clarifying,
  onAnswer,
}: {
  clarifying: ClarifyingQuestion;
  onAnswer: (text: string) => void;
}) {
  return (
    <div className="clarifying-card">
      <div className="clarifying-card__question">{clarifying.question}</div>
      <div className="clarifying-card__options">
        {clarifying.options.map((option, i) => (
          <button
            type="button"
            key={`${option.slate}-${option.take}`}
            className={i === 0 ? "clarifying-option clarifying-option--first" : "clarifying-option"}
            onClick={() => onAnswer(`Slate ${option.slate}, take ${option.take}`)}
          >
            <span className="clarifying-option__label mono">
              {option.slate} · T{option.take}
            </span>
            {(option.reel || option.timecodeShort) && (
              <span className="clarifying-option__sub mono">
                {[option.reel, option.timecodeShort].filter(Boolean).join(" · ")}
              </span>
            )}
          </button>
        ))}
      </div>
      {clarifying.reason && <div className="clarifying-card__reason">{clarifying.reason}</div>}
    </div>
  );
}
