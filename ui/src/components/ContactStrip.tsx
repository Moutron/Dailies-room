import { useEffect, useState } from "react";
import { getThumbnails, timecodeToSeconds } from "../api";
import type { Thumbnail } from "../types";

/** A horizontal row of frames with the timecode printed beneath each — the
 * signature element from ui/DESIGN.md. Clicking a frame plays the clip from
 * that timecode. */
export function ContactStrip({
  clipId,
  onSeek,
}: {
  clipId: string;
  onSeek: (clipId: string, seconds: number) => void;
}) {
  const [frames, setFrames] = useState<Thumbnail[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getThumbnails(clipId).then((f) => {
      if (!cancelled) setFrames(f);
    });
    return () => {
      cancelled = true;
    };
  }, [clipId]);

  if (frames === null) return <div className="contact-strip contact-strip--loading" aria-hidden="true" />;
  if (frames.length === 0) return null;

  return (
    <div className="contact-strip" role="group" aria-label={`Frames from ${clipId}`}>
      {frames.map((f) => (
        <button
          key={f.file}
          type="button"
          className="contact-strip__frame"
          onClick={() => onSeek(clipId, timecodeToSeconds(f.timecode))}
        >
          <img src={`/thumbs/${f.file}`} alt="" loading="lazy" />
          <span className="mono contact-strip__tc">{f.timecode}</span>
        </button>
      ))}
    </div>
  );
}
