import { useEffect, useRef, useState } from "react";
import { getClipMeta, getClipUrl, getPosterUrl } from "../api";
import { formatDuration, sceneLabel, shotTypeLabel } from "../agentCopy";
import type { ActiveClip, ClipMeta } from "../types";

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export function Viewer({
  active,
  onMetaLoaded,
}: {
  active: ActiveClip | null;
  onMetaLoaded?: (meta: ClipMeta | null) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [meta, setMeta] = useState<ClipMeta | null>(null);
  const [loadedClipId, setLoadedClipId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    if (active.clipId !== loadedClipId) {
      setError(null);
      setMeta(null);
      Promise.all([getClipUrl(active.clipId), getClipMeta(active.clipId)])
        .then(([url, m]) => {
          if (cancelled) return;
          setSrc(url);
          setMeta(m);
          setLoadedClipId(active.clipId);
          onMetaLoaded?.(m);
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

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  }

  function seekToFraction(fraction: number) {
    const video = videoRef.current;
    if (!video || !duration) return;
    video.currentTime = fraction * duration;
  }

  return (
    <div className="viewer">
      <div className="viewer__header">
        <span className="viewer__label mono">VIEWER</span>
        {active && <span className="viewer__clip-id mono">{active.clipId}</span>}
        <div className="viewer__spacer" />
        {active && <span className="viewer__signed mono">SIGNED URL</span>}
      </div>

      <div className="viewer__player-block">
        <div className="viewer__frame">
          {!active ? (
            <div className="viewer__placeholder">
              <span className="mono">NO CLIP LOADED</span>
              <span className="mono viewer__placeholder-sub">Click a result to play it here.</span>
            </div>
          ) : error ? (
            <div className="viewer__placeholder" role="alert">
              <span className="mono">PLAYBACK FAILED</span>
              <span className="mono viewer__placeholder-sub">{error}</span>
            </div>
          ) : (
            <video
              ref={videoRef}
              key={active.clipId}
              src={src ?? undefined}
              poster={getPosterUrl(active.clipId)}
              onLoadedMetadata={(e) => {
                setDuration(e.currentTarget.duration);
                seekAndPlay();
              }}
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onError={() => setError("Playback failed — the signed URL may have expired.")}
            />
          )}
          {meta && (
            <span className={meta.dialogue_count === 0 ? "viewer__badge viewer__badge--accent mono" : "viewer__badge mono"}>
              {shotTypeLabel(meta.shot_type ?? undefined)} · {formatDuration(meta.duration_s)}
            </span>
          )}
        </div>

        {active && !error && (
          <div className="viewer__transport">
            <button type="button" className="viewer__play" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
              {playing ? "❙❙" : "▶"}
            </button>
            <button
              type="button"
              className="viewer__track"
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                seekToFraction((e.clientX - rect.left) / rect.width);
              }}
              aria-label="Seek"
            >
              <span
                className="viewer__track-fill"
                style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
              />
            </button>
            <span className="viewer__time mono">
              {formatClock(currentTime)} / {formatClock(duration)}
            </span>
          </div>
        )}
      </div>

      {meta && meta.dialogue_count === 0 && (
        <>
          <div className="viewer__divider" />
          <div className="viewer__transcript">
            <div className="viewer__section-label mono">TRANSCRIPT</div>
            <div className="viewer__transcript-empty">
              <span className="mono">EMPTY</span>
              <span className="viewer__transcript-empty-body">
                No speech detected on A or B channel. This take was never transcribed.
              </span>
            </div>
          </div>
        </>
      )}

      {meta && (
        <>
          <div className="viewer__divider" />
          <div className="viewer__slate">
            <div className="viewer__section-label mono">SLATE</div>
            <div className="viewer__slate-grid">
              <div>
                <div className="viewer__field-caption mono">SCENE</div>
                <div className="viewer__field-value mono">{sceneLabel(meta)}</div>
              </div>
              <div>
                <div className="viewer__field-caption mono">SLATE / TAKE</div>
                <div className="viewer__field-value mono">
                  {meta.slate} / {meta.take}
                </div>
              </div>
              <div>
                <div className="viewer__field-caption mono">CAMERA</div>
                <div className="viewer__field-value mono">{meta.camera_movement ?? "—"}</div>
              </div>
              <div>
                <div className="viewer__field-caption mono">DURATION</div>
                <div className="viewer__field-value mono">{formatDuration(meta.duration_s)}</div>
              </div>
            </div>
          </div>

          <div className="viewer__divider" />
          <div className="viewer__gemini">
            <span className="viewer__section-label mono">WHAT GEMINI SAW</span>
            {meta.description && <p className="viewer__description">{meta.description}</p>}
            {meta.notable_elements && meta.notable_elements.length > 0 && (
              <div className="viewer__tags">
                {meta.notable_elements.map((tag) => (
                  <span key={tag} className="viewer__tag mono">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
