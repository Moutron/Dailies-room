import { useRef, useState } from "react";
import { uploadFootage } from "../api";
import type { UploadMetadata, UploadPayload } from "../types";

type Mode = "mp4" | "frames";
type Status = "idle" | "uploading" | "error";

function ModeToggle({ mode, onToggle }: { mode: Mode; onToggle: () => void }) {
  return (
    <button type="button" className="ingest-upload__mode mono" onClick={onToggle}>
      {mode === "mp4" ? "MP4" : "FRAME SEQUENCE"}
    </button>
  );
}

const EMPTY_META = {
  clipId: "",
  scene: "",
  slate: "",
  take: "",
  reel: "",
  tcStartS: "",
  location: "",
  dayNight: "",
  intExt: "",
  charactersExpected: "",
  fps: "24",
};

/** Screen #6's upload form -- takes either a direct mp4 or a still-frame
 * sequence (encoded server-side, pipeline/encode.py) and runs it through
 * the real pipeline synchronously (POST /ingest/upload). There is no
 * observable server-side stage over a single synchronous request, so this
 * shows one honest "indexing" state rather than a fake multi-stage
 * animation -- see ui/server/ingest.py's module docstring for why the page
 * above this form doesn't fabricate in-flight rows either. */
export function IngestUpload({ onUploaded }: { onUploaded: () => void }) {
  const [mode, setMode] = useState<Mode>("mp4");
  const [meta, setMeta] = useState(EMPTY_META);
  const [mp4File, setMp4File] = useState<File | null>(null);
  const [frameFiles, setFrameFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);
  const sessionId = useRef(crypto.randomUUID());

  const hasFile = mode === "mp4" ? mp4File != null : frameFiles.length > 0;
  const requiredFilled = meta.clipId.trim() !== "" && meta.scene.trim() !== "" && meta.slate.trim() !== "" && meta.take.trim() !== "";
  const canSubmit = requiredFilled && hasFile && status !== "uploading";

  const fpsNumber = Number(meta.fps);
  const frameDurationS =
    mode === "frames" && frameFiles.length > 0 && fpsNumber > 0 ? frameFiles.length / fpsNumber : null;

  function setField<K extends keyof typeof EMPTY_META>(key: K, value: string) {
    setMeta((m) => ({ ...m, [key]: value }));
  }

  function switchMode() {
    setMode((m) => (m === "mp4" ? "frames" : "mp4"));
    setMp4File(null);
    setFrameFiles([]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    setStatus("uploading");
    setErrorText(null);

    const uploadMeta: UploadMetadata = meta;
    const payload: UploadPayload =
      mode === "mp4" ? { mode: "mp4", file: mp4File as File } : { mode: "frames", files: frameFiles };

    const result = await uploadFootage(uploadMeta, payload, sessionId.current);

    if (!result.ok) {
      setStatus("error");
      setErrorText(result.error);
      return;
    }

    setStatus("idle");
    setMeta(EMPTY_META);
    setMp4File(null);
    setFrameFiles([]);
    onUploaded();
  }

  return (
    <form className="ingest-upload" onSubmit={handleSubmit}>
      <div className="ingest-upload__header">
        <span className="ingest-upload__overline mono">UPLOAD FOOTAGE</span>
        <ModeToggle mode={mode} onToggle={switchMode} />
      </div>

      <div className="ingest-upload__file">
        {mode === "mp4" ? (
          <input
            type="file"
            accept="video/mp4,.mp4"
            aria-label="MP4 file"
            onChange={(e) => setMp4File(e.target.files?.[0] ?? null)}
          />
        ) : (
          <input
            type="file"
            accept="image/jpeg,image/png,.jpg,.jpeg,.png"
            aria-label="Frame files"
            multiple
            onChange={(e) => setFrameFiles(Array.from(e.target.files ?? []))}
          />
        )}
      </div>

      {mode === "frames" && (
        <div className="ingest-upload__frames-info mono">
          <span>{frameFiles.length} FRAMES</span>
          <label className="ingest-upload__fps-label">
            FPS
            <input
              type="number"
              min={1}
              className="ingest-upload__fps-input"
              value={meta.fps}
              onChange={(e) => setField("fps", e.target.value)}
            />
          </label>
          <span>{frameDurationS != null ? `${frameDurationS.toFixed(2)}s` : "—"}</span>
        </div>
      )}

      <div className="ingest-upload__fields">
        <input
          placeholder="clip_id *"
          value={meta.clipId}
          onChange={(e) => setField("clipId", e.target.value)}
          required
        />
        <input
          placeholder="scene *"
          value={meta.scene}
          onChange={(e) => setField("scene", e.target.value)}
          required
        />
        <input
          placeholder="slate *"
          value={meta.slate}
          onChange={(e) => setField("slate", e.target.value)}
          required
        />
        <input
          placeholder="take *"
          value={meta.take}
          onChange={(e) => setField("take", e.target.value)}
          required
        />
        <input placeholder="reel" value={meta.reel} onChange={(e) => setField("reel", e.target.value)} />
        <input
          placeholder="tc_start_s"
          value={meta.tcStartS}
          onChange={(e) => setField("tcStartS", e.target.value)}
        />
        <input
          placeholder="location"
          value={meta.location}
          onChange={(e) => setField("location", e.target.value)}
        />
        <input
          placeholder="day/night"
          value={meta.dayNight}
          onChange={(e) => setField("dayNight", e.target.value)}
        />
        <input placeholder="int/ext" value={meta.intExt} onChange={(e) => setField("intExt", e.target.value)} />
        <input
          placeholder="characters expected"
          value={meta.charactersExpected}
          onChange={(e) => setField("charactersExpected", e.target.value)}
        />
      </div>

      {status === "uploading" && (
        <div className="ingest-upload__status mono">Indexing — this takes a minute.</div>
      )}
      {status === "error" && errorText && <div className="ingest-upload__error mono">{errorText}</div>}

      <button type="submit" className="ingest-upload__submit mono" disabled={!canSubmit}>
        {status === "uploading" ? "UPLOADING…" : "UPLOAD"}
      </button>
    </form>
  );
}
