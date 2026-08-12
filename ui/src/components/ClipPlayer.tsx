import { useEffect, useRef, useState } from "react";
import { getClipUrl } from "../api";
import type { ActiveClip } from "../types";

/** A video element that loads whatever clip is active and seeks to the
 * requested timecode as soon as it can. Pinned in the layout so seeking to
 * a new result never gets scrolled out of view (see ui/DESIGN.md). */
export function ClipPlayer({ active }: { active: ActiveClip | null }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [loadedClipId, setLoadedClipId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    if (active.clipId !== loadedClipId) {
      setError(null);
      getClipUrl(active.clipId)
        .then((url) => {
          if (!cancelled) {
            setSrc(url);
            setLoadedClipId(active.clipId);
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err.message ?? "Could not load this clip.");
        });
    } else {
      seekAndPlay();
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.clipId, active?.nonce]);

  function seekAndPlay() {
    const video = videoRef.current;
    if (!video || !active) return;
    video.currentTime = active.seekSeconds;
    video.play().catch(() => {
      /* autoplay can be blocked before a user gesture; the player still
         lands on the right frame, which is the part that matters */
    });
  }

  if (!active) {
    return (
      <div className="clip-player clip-player--empty">
        <p>No clip selected. Click a result to play it here.</p>
      </div>
    );
  }

  return (
    <div className="clip-player">
      <div className="clip-player__slate">
        <span className="mono">{active.clipId}</span>
      </div>
      {error ? (
        <div className="clip-player__error" role="alert">
          <strong>Couldn't load this clip.</strong> {error} Try clicking the result again.
        </div>
      ) : (
        <video
          ref={videoRef}
          key={active.clipId}
          src={src ?? undefined}
          controls
          onLoadedMetadata={seekAndPlay}
          onError={() => setError("Playback failed — the signed URL may have expired.")}
        />
      )}
    </div>
  );
}
