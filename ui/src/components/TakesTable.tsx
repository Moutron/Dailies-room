import { timecodeToSeconds } from "../api";
import { formatDuration, shotTypeLabel } from "../agentCopy";
import type { ResultRow } from "../types";

interface Column {
  header: string;
  /** Grid track width — 1fr for the one prose column, a fixed px width for
   * everything else, matching the handoff's 132/104/68/58/1fr layout. */
  width: string;
  render: (row: ResultRow) => string;
  /** The prose column (PERFORMANCE NOTE / LINE / DESCRIPTION) renders in
   * Archivo like body text; every other column is JetBrains Mono data. */
  prose?: boolean;
}

function noteFor(row: ResultRow): string {
  if (row.dominant_mood || row.technical_notes?.length) {
    const parts = [row.dominant_mood ? `Reads ${row.dominant_mood}.` : null, ...(row.technical_notes ?? [])];
    return parts.filter(Boolean).join(" ");
  }
  return row.summary ?? "—";
}

const COLUMNS_BY_TOOL: Record<string, Column[]> = {
  search_dialogue: [
    { header: "CLIP", width: "132px", render: (r) => r.clip_id ?? "—" },
    { header: "TIMECODE", width: "104px", render: (r) => r.timecode_in ?? "—" },
    { header: "SPEAKER", width: "68px", render: (r) => r.speaker ?? "—" },
    {
      header: "LINE",
      width: "1fr",
      prose: true,
      render: (r) => (r.text ? `"${r.text}"${r.delivery ? ` — ${r.delivery}` : ""}` : "—"),
    },
  ],
  search_visuals: [
    { header: "CLIP", width: "132px", render: (r) => r.clip_id ?? "—" },
    { header: "TIMECODE", width: "104px", render: (r) => r.timecode_in ?? "—" },
    { header: "SHOT", width: "68px", render: (r) => shotTypeLabel(r.shot_type) },
    { header: "DESCRIPTION", width: "1fr", prose: true, render: (r) => r.description ?? "—" },
  ],
  get_coverage: [
    { header: "CLIP", width: "132px", render: (r) => r.clip_id ?? "—" },
    { header: "TIMECODE", width: "104px", render: (r) => r.timecode_in ?? "—" },
    { header: "SHOT", width: "68px", render: (r) => shotTypeLabel(r.shot_type) },
    { header: "DUR", width: "58px", render: (r) => formatDuration(r.duration_s) },
    { header: "PERFORMANCE NOTE", width: "1fr", prose: true, render: noteFor },
  ],
  compare_takes: [
    { header: "CLIP", width: "132px", render: (r) => r.clip_id ?? "—" },
    { header: "TIMECODE", width: "104px", render: (r) => r.timecode_in ?? "—" },
    { header: "SHOT", width: "68px", render: (r) => shotTypeLabel(r.shot_type) },
    { header: "DUR", width: "58px", render: (r) => formatDuration(r.duration_s) },
    { header: "PERFORMANCE NOTE", width: "1fr", prose: true, render: noteFor },
  ],
};

export function TakesTable({
  tool,
  rows,
  onSeek,
  circledClipIds,
}: {
  tool: string;
  rows: ResultRow[];
  onSeek: (clipId: string, seconds: number) => void;
  /** Real clip_ids currently circled (circled_takes, via GET /clips) — a
   * row only highlights when its clip_id is actually in this set. */
  circledClipIds?: Set<string>;
}) {
  if (rows.length === 0) return null;
  const columns = COLUMNS_BY_TOOL[tool] ?? COLUMNS_BY_TOOL.search_visuals;
  const gridTemplateColumns = columns.map((c) => c.width).join(" ");

  return (
    <div className="takes-table">
      <div className="takes-table__header" style={{ gridTemplateColumns }}>
        {columns.map((c) => (
          <span key={c.header}>{c.header}</span>
        ))}
      </div>
      {rows.map((row, i) => {
        const clipId = row.clip_id;
        const seekable = clipId && row.timecode_in;
        const circled = !!clipId && !!circledClipIds?.has(clipId);
        return (
          <button
            type="button"
            key={clipId ?? i}
            className={circled ? "takes-table__row takes-table__row--circled" : "takes-table__row"}
            style={{ gridTemplateColumns }}
            disabled={!seekable}
            onClick={() => seekable && onSeek(clipId, timecodeToSeconds(row.timecode_in!))}
          >
            {columns.map((c) => (
              <span
                key={c.header}
                className={c.prose ? "takes-table__cell takes-table__cell--prose" : "takes-table__cell mono"}
              >
                {c.render(row)}
              </span>
            ))}
          </button>
        );
      })}
    </div>
  );
}
