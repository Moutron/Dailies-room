import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getClipDialogue, getClipMeta, getClipUrl, getPosterUrl, secondsToTimecode, setCircled } from "../api";
import { formatDuration, sceneLabel, shotTypeLabel } from "../agentCopy";
import { activeLineIndex, formatIngestedAt, lineDurationLabel, regionStyle } from "../clipDetail";
import type { ClipMeta, DialogueLine } from "../types";

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export function ClipDetailPage() {
  const { clipId } = useParams<{ clipId: string }>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [meta, setMeta] = useState<ClipMeta | null>(null);
  const [lines, setLines] = useState<DialogueLine[] | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!clipId) return;
    let cancelled = false;
    setError(null);
    setNotFound(false);
    setMeta(null);
    setLines(null);
    Promise.all([getClipUrl(clipId), getClipMeta(clipId), getClipDialogue(clipId)])
      .then(([url, m, dialogueLines]) => {
        if (cancelled) return;
        if (!m) {
          setNotFound(true);
          return;
        }
        setSrc(url);
        setMeta(m);
        setLines(dialogueLines ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "Could not load this clip.");
      });
    return () => {
      cancelled = true;
    };
  }, [clipId]);

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  }

  function seekTo(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    video.play().catch(() => {});
  }

  function seekToFraction(fraction: number) {
    const video = videoRef.current;
    if (!video || !meta?.duration_s) return;
    seekTo(fraction * meta.duration_s);
  }

  function copyTimecode() {
    if (!meta) return;
    const tc = secondsToTimecode(currentTime, meta.tc_start_s);
    navigator.clipboard?.writeText(tc).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  function toggleCircled() {
    if (!meta || !clipId) return;
    const next = !meta.circled;
    setMeta({ ...meta, circled: next });
    setCircled(clipId, next).then((circled) => {
      if (circled == null) setMeta((m) => (m ? { ...m, circled: !next } : m));
    });
  }

  if (!clipId) return null;

  if (notFound) {
    return (
      <div className="clip-detail">
        <div className="clip-detail__header">
          <Link to="/ask" className="clip-detail__back mono" aria-label="Back">
            ←
          </Link>
          <span className="clip-detail__crumb mono">Clip not found: {clipId}</span>
        </div>
      </div>
    );
  }

  const activeIdx = lines ? activeLineIndex(lines, currentTime) : -1;
  const duration = meta?.duration_s ?? 0;
  const rulerMid = duration / 2;

  return (
    <div className="clip-detail">
      <div className="clip-detail__header">
        <Link to="/ask" className="clip-detail__back mono" aria-label="Back">
          ←
        </Link>
        <nav className="clip-detail__crumb mono" aria-label="Context">
          <span>REELS</span>
          <span className="clip-detail__crumb-sep">/</span>
          <span>{meta?.reel ?? "—"}</span>
          <span className="clip-detail__crumb-sep">/</span>
          <span className="clip-detail__crumb--active">{clipId}</span>
        </nav>
        <div className="clip-detail__spacer" />
        <div className="clip-detail__actions">
          <button type="button" className="clip-detail__btn" onClick={copyTimecode} disabled={!meta}>
            {copied ? "Copied" : "Copy timecode"}
          </button>
          <button
            type="button"
            className="clip-detail__btn clip-detail__btn--primary"
            onClick={toggleCircled}
            disabled={!meta}
          >
            {meta?.circled ? "Circled ✓" : "Circle take"}
          </button>
        </div>
      </div>

      <div className="clip-detail__body">
        <div className="clip-detail__left">
          <div className="clip-detail__player">
            {error ? (
              <div className="clip-detail__player-placeholder" role="alert">
                <span className="mono">PLAYBACK FAILED</span>
                <span>{error}</span>
              </div>
            ) : (
              <video
                ref={videoRef}
                src={src ?? undefined}
                poster={getPosterUrl(clipId)}
                onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onError={() => setError("Playback failed — the signed URL may have expired.")}
              />
            )}
            {meta && (
              <span className="clip-detail__badge mono">
                SC {meta.scene} · {meta.slate} · T{meta.take}
                {meta.circled ? " · CIRCLED" : ""}
              </span>
            )}
          </div>

          <div className="clip-detail__transport-block">
            <div className="clip-detail__transport">
              <button
                type="button"
                className="clip-detail__play"
                onClick={togglePlay}
                aria-label={playing ? "Pause" : "Play"}
                disabled={!meta}
              >
                {playing ? "❙❙" : "▶"}
              </button>
              <span className="clip-detail__timecode mono">
                {meta ? secondsToTimecode(currentTime, meta.tc_start_s) : "—"}
              </span>
              <div className="clip-detail__track-col">
                <button
                  type="button"
                  className="clip-detail__track"
                  onClick={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    seekToFraction((e.clientX - rect.left) / rect.width);
                  }}
                  aria-label="Seek"
                >
                  {lines?.map((line) => {
                    const style = regionStyle(line, duration);
                    return (
                      <span
                        key={line.segment_idx}
                        role="button"
                        tabIndex={-1}
                        className="clip-detail__region"
                        style={style}
                        aria-label={`Seek to ${line.speaker}'s line`}
                        onClick={(e) => {
                          e.stopPropagation();
                          seekTo(line.start_s);
                        }}
                      />
                    );
                  })}
                  <span
                    className="clip-detail__playhead"
                    style={{ left: `${duration ? (currentTime / duration) * 100 : 0}%` }}
                  />
                </button>
                <div className="clip-detail__ruler mono">
                  <span>{formatClock(0)}</span>
                  <span>{formatClock(rulerMid)}</span>
                  <span>{formatClock(duration)}</span>
                </div>
              </div>
            </div>
            <div className="clip-detail__caption mono">HIGHLIGHTED REGIONS = TRANSCRIBED DIALOGUE</div>
          </div>

          {meta && (
            <>
              <div className="clip-detail__divider" />
              <div className="clip-detail__meta-strip">
                <div className="clip-detail__meta-field">
                  <span className="clip-detail__meta-caption mono">SCENE</span>
                  <span className="clip-detail__meta-value mono">{sceneLabel(meta)}</span>
                </div>
                <div className="clip-detail__meta-field">
                  <span className="clip-detail__meta-caption mono">DURATION</span>
                  <span className="clip-detail__meta-value mono">{formatDuration(meta.duration_s)}</span>
                </div>
                <div className="clip-detail__meta-field">
                  <span className="clip-detail__meta-caption mono">REEL</span>
                  <span className="clip-detail__meta-value mono">{meta.reel}</span>
                </div>
                <div className="clip-detail__meta-field">
                  <span className="clip-detail__meta-caption mono">SHOT TYPE</span>
                  <span className="clip-detail__meta-value mono">{shotTypeLabel(meta.shot_type ?? undefined)}</span>
                </div>
                <div className="clip-detail__meta-field">
                  <span className="clip-detail__meta-caption mono">INGESTED</span>
                  <span className="clip-detail__meta-value mono">{formatIngestedAt(meta.ingested_at)}</span>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="clip-detail__right">
          <div className="clip-detail__transcript-header">
            <span className="clip-detail__transcript-label mono">TRANSCRIPT</span>
            <span className="clip-detail__transcript-count mono">
              {lines ? `${lines.length} LINE${lines.length === 1 ? "" : "S"} · GEMINI` : "—"}
            </span>
          </div>

          {lines && lines.length === 0 ? (
            <div className="clip-detail__transcript-empty-wrap">
              <div className="viewer__transcript-empty">
                <span className="mono">EMPTY</span>
                <span className="viewer__transcript-empty-body">
                  No speech detected on A or B channel. This take was never transcribed.
                </span>
              </div>
            </div>
          ) : (
            <div className="clip-detail__lines">
              {lines?.map((line, i) => {
                const active = i === activeIdx;
                return (
                  <button
                    key={line.segment_idx}
                    type="button"
                    className={active ? "clip-detail__line clip-detail__line--active" : "clip-detail__line"}
                    onClick={() => seekTo(line.start_s)}
                  >
                    <span className="clip-detail__line-tc mono">
                      {meta ? secondsToTimecode(line.start_s, meta.tc_start_s) : "—"}
                    </span>
                    <span className="clip-detail__line-body">
                      <span className="clip-detail__line-speaker mono">{line.speaker}</span>
                      <span className="clip-detail__line-text">{line.text}</span>
                      {active && (
                        <span className="clip-detail__line-pills">
                          <span className="clip-detail__pill clip-detail__pill--accent mono">{line.delivery}</span>
                          <span className="clip-detail__pill mono">{lineDurationLabel(line)}</span>
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
