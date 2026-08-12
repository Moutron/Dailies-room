import { timecodeToSeconds } from "../api";
import type { ResultRow } from "../types";
import { ContactStrip } from "./ContactStrip";

function slateCode(row: ResultRow): string {
  const parts = [row.scene, row.slate, row.take !== undefined ? `T${row.take}` : null].filter(
    Boolean
  );
  return parts.join(" · ") || "—";
}

/** The line that actually says what this result is — whichever field the
 * source tool populated. Dialogue rows get their line + delivery note;
 * visual/coverage/take rows get their description/summary/mood. */
function primaryText(row: ResultRow): string | null {
  if (row.text) return row.delivery ? `"${row.text}" — ${row.delivery}` : `"${row.text}"`;
  if (row.description) return row.description;
  if (row.summary) return row.summary;
  if (row.dominant_mood) return `Reads ${row.dominant_mood}.`;
  return null;
}

function gapLines(row: ResultRow): string[] {
  const lines: string[] = [];
  if (row.never_appeared?.length) lines.push(`Never made it into a shot: ${row.never_appeared.join(", ")}.`);
  if (row.no_tight_shot?.length) lines.push(`No close-up: ${row.no_tight_shot.join(", ")}.`);
  if (row.wide_coverage?.length) lines.push(`Only caught in wides: ${row.wide_coverage.join(", ")}.`);
  return lines;
}

export function ResultCard({
  row,
  onSeek,
}: {
  row: ResultRow;
  onSeek: (clipId: string, seconds: number) => void;
}) {
  if (row.error) {
    return (
      <div className="result-card result-card--error" role="alert">
        {row.error}
      </div>
    );
  }

  const clipId = row.clip_id;
  const text = primaryText(row);
  const gaps = gapLines(row);

  function playFromIn() {
    if (clipId && row.timecode_in) onSeek(clipId, timecodeToSeconds(row.timecode_in));
  }

  return (
    <article className="result-card">
      <header className="result-card__header">
        <span className="mono result-card__slate">{slateCode(row)}</span>
        {row.timecode_in && (
          <button type="button" className="mono result-card__timecode" onClick={playFromIn}>
            {row.timecode_in} → {row.timecode_out}
          </button>
        )}
        {row.shot_type && <span className="result-card__tag">{row.shot_type.replace(/_/g, " ")}</span>}
      </header>

      {text && <p className="result-card__text">{text}</p>}

      {row.technical_notes && row.technical_notes.length > 0 && (
        <ul className="result-card__flags">
          {row.technical_notes.map((note, i) => (
            <li key={i} className="flag-note">
              {note}
            </li>
          ))}
        </ul>
      )}

      {gaps.length > 0 && (
        <ul className="result-card__flags">
          {gaps.map((g, i) => (
            <li key={i} className="flag-note">
              {g}
            </li>
          ))}
        </ul>
      )}

      {row.dialogue && row.dialogue.length > 0 && (
        <ul className="result-card__lines">
          {row.dialogue.map((line, i) => (
            <li key={i}>
              {line.timecode_in && clipId && (
                <button
                  type="button"
                  className="mono"
                  onClick={() => onSeek(clipId, timecodeToSeconds(line.timecode_in!))}
                >
                  {line.timecode_in}
                </button>
              )}{" "}
              <span className="result-card__speaker">{line.speaker}:</span> "{line.text}"
              {line.delivery ? ` — ${line.delivery}` : ""}
            </li>
          ))}
        </ul>
      )}

      {clipId && <ContactStrip clipId={clipId} onSeek={onSeek} />}
    </article>
  );
}
