import { getPosterUrl, timecodeToSeconds } from "../api";
import { formatDuration, shotTypeLabel } from "../agentCopy";
import type { NoDialogueAnswer } from "../agentCopy";

/** Screen #1b's honesty card: a deliberately grey left bar (an absence, not
 * a finding), the model's own answer laid out at two type scales — the
 * headline gets the largest type in the app outside page titles. */
export function NoDialogueCard({ answer }: { answer: NoDialogueAnswer }) {
  const { headline, body } = answer;
  return (
    <div className="no-dialogue-card">
      <div className="no-dialogue-card__bar" aria-hidden="true" />
      <div className="no-dialogue-card__body">
        <div className="no-dialogue-card__overline mono">NO DIALOGUE IN THIS TAKE</div>
        <div className="no-dialogue-card__headline">{headline}</div>
        {body && <div className="no-dialogue-card__substitute">{body}</div>}
      </div>
    </div>
  );
}

/** A working clip strip built from the real poster frame — never the
 * mockup's fabricated "VFX PLATE" placeholder. Sits below NoDialogueCard as
 * a second panel, matching the handoff's two stacked-but-distinct blocks. */
export function NoDialogueClipStrip({
  clip,
  onSeek,
}: {
  clip: NoDialogueAnswer["clip"];
  onSeek: (clipId: string, seconds: number) => void;
}) {
  if (!clip?.clip_id) return null;
  const clipId = clip.clip_id;
  const seekable = clip.timecode_in;

  return (
    <div className="clip-strip">
      <img className="clip-strip__thumb" src={getPosterUrl(clipId)} alt="" />
      <div className="clip-strip__meta">
        <span className="clip-strip__id mono">{clipId}</span>
        <span className="clip-strip__line mono">
          {clip.timecode_in ?? "—"} · {formatDuration(clip.duration_s)} · {shotTypeLabel(clip.shot_type)}
        </span>
        <span className="clip-strip__hint">Play the clip and see for yourself</span>
      </div>
      <button
        type="button"
        className="clip-strip__play"
        disabled={!seekable}
        aria-label={`Play ${clipId}`}
        onClick={() => seekable && onSeek(clipId, timecodeToSeconds(clip.timecode_in!))}
      >
        ▶
      </button>
    </div>
  );
}
