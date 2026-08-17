import { Fragment, useCallback, useEffect, useState } from "react";
import { getIngestSummary } from "../api";
import { formatDuration } from "../agentCopy";
import { formatIngestedAt } from "../clipDetail";
import { IngestUpload } from "../components/IngestUpload";
import { Shell } from "../shell/Shell";
import type { IngestClip, IngestSummary } from "../types";

const PIPELINE_STAGES = [
  { number: "01", label: "CARD OFFLOAD", body: "Clip lands in Cloud Storage" },
  { number: "02", label: "GEMINI WATCHES", body: "Transcript, performance, what's on screen" },
  { number: "03", label: "EMBED", body: "Dialogue + visual vectors" },
  { number: "04", label: "CLICKHOUSE", body: "Metadata beside the vectors, one table" },
] as const;

function PipelineCard({ number, label, body, accent }: { number: string; label: string; body: string; accent?: boolean }) {
  return (
    <div className={accent ? "ingest-strip__card ingest-strip__card--accent" : "ingest-strip__card"}>
      <span className="ingest-strip__label mono">
        {number} · {label}
      </span>
      <span className="ingest-strip__body">{body}</span>
    </div>
  );
}

function IngestRow({ clip }: { clip: IngestClip }) {
  return (
    <div className="ingest-table__row" role="row">
      <span className="ingest-table__clip-id mono">{clip.clip_id}</span>
      <span className="ingest-table__duration mono">{formatDuration(clip.duration_s)}</span>
      <div className="ingest-table__stage">
        <div className="ingest-table__track">
          <div className="ingest-table__track-fill" style={{ width: "100%" }} />
        </div>
        <span className="ingest-table__phrase mono">indexed</span>
      </div>
      <span className="ingest-table__lines mono">{clip.dialogue_count}</span>
      <span className="ingest-table__state mono">{clip.state}</span>
    </div>
  );
}

export function IngestPage() {
  const [summary, setSummary] = useState<IngestSummary | null>(null);
  const [error, setError] = useState(false);

  const refetch = useCallback(() => {
    getIngestSummary().then((s) => {
      if (!s) {
        setError(true);
        return;
      }
      setError(false);
      setSummary(s);
    });
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const railStats = summary && (
    <>
      <div className="left-rail__stat">
        <div className="left-rail__stat-caption mono">INDEXED TODAY</div>
        <div className="left-rail__stat-value mono">{summary.indexed_today}</div>
      </div>
      <div className="left-rail__stat">
        <div className="left-rail__stat-caption mono">EMBEDDINGS</div>
        <div className="left-rail__stat-value mono">{summary.embeddings}</div>
      </div>
    </>
  );

  return (
    <Shell filters={railStats}>
      <div className="ingest-page">
        <IngestUpload onUploaded={refetch} />
        {error && <p className="ingest-page__error">Could not load the pipeline index.</p>}
        {summary && (
          <>
            <div className="ingest-page__header">
              <div className="ingest-page__heading">
                <div className="ingest-page__overline mono">PIPELINE · PER CLIP</div>
                <h1 className="ingest-page__headline">
                  Nothing here is
                  <br />
                  specific to six clips.
                </h1>
              </div>
              <div className="ingest-page__spacer" />
              <div
                className="ingest-page__badge"
                title={
                  summary.most_recent_ingested_at
                    ? `Most recently indexed ${formatIngestedAt(summary.most_recent_ingested_at)}`
                    : undefined
                }
              >
                <span className="ingest-page__badge-dot" aria-hidden="true" />
                <span className="ingest-page__badge-text mono">INDEXED {summary.indexed_today}</span>
              </div>
            </div>

            <div className="ingest-strip">
              {PIPELINE_STAGES.map((stage, i) => (
                <Fragment key={stage.number}>
                  <PipelineCard {...stage} accent={i === PIPELINE_STAGES.length - 1} />
                  {i < PIPELINE_STAGES.length - 1 && (
                    <span className="ingest-strip__arrow mono" aria-hidden="true">
                      →
                    </span>
                  )}
                </Fragment>
              ))}
            </div>

            <div className="ingest-table" role="table">
              <div className="ingest-table__row ingest-table__row--header" role="row">
                <span>CLIP</span>
                <span>DURATION</span>
                <span>STAGE</span>
                <span>LINES</span>
                <span className="ingest-table__state-header">STATE</span>
              </div>
              {summary.clips.map((clip) => (
                <IngestRow key={clip.clip_id} clip={clip} />
              ))}
            </div>
          </>
        )}
      </div>
    </Shell>
  );
}
