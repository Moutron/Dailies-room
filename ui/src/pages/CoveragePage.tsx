import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getClipList, getCoverageMatrix } from "../api";
import { rowLabel, statusHoverText } from "../coverageMatrix";
import { Shell } from "../shell/Shell";
import type { CoverageMatrix, CoverageMatrixRow } from "../types";

function TakeChip({ clipId, circled }: { clipId: string; circled: boolean }) {
  return (
    <Link
      to={`/clip/${encodeURIComponent(clipId)}`}
      className={circled ? "coverage-matrix__chip coverage-matrix__chip--circled mono" : "coverage-matrix__chip mono"}
    >
      {clipId}
      {circled && <span className="coverage-matrix__chip-star"> ★</span>}
    </Link>
  );
}

function GapCell({ column, row, sql }: { column: string; row: CoverageMatrixRow; sql: string }) {
  // Real per-row flagging, not per-cell: a row lands on the shot list as a
  // whole (ui/server/shot_list.py generates one row per flagged (scene,
  // slate)), so only cells belonging to an actually-flagged row link
  // there -- an empty cell in a COMPLETE row (e.g. S03/2C's WIDE column)
  // is a real gap in that one shot size, but not one this product tracks
  // as a pickup.
  if (row.classification == null) {
    return (
      <div
        className="coverage-matrix__gap-cell"
        role="presentation"
        title={`No ${column} take for ${rowLabel(row)}.`}
      />
    );
  }
  return (
    <Link
      to="/shot-list"
      className="coverage-matrix__gap-cell coverage-matrix__gap-cell--flagged"
      title={`No ${column} take for ${rowLabel(row)} — this row is on the shot list (${row.classification}).\n\n${sql.trim()}`}
    />
  );
}

function MatrixRow({
  row,
  columns,
  sql,
  circledClipIds,
}: {
  row: CoverageMatrixRow;
  columns: string[];
  sql: string;
  circledClipIds: Set<string>;
}) {
  const isGap = row.status !== "COMPLETE";
  return (
    <div className="coverage-matrix__row" role="row">
      <div className="coverage-matrix__row-label">
        <span className="coverage-matrix__slate mono">{rowLabel(row)}</span>
        <span className="coverage-matrix__desc">{row.description}</span>
      </div>
      {columns.map((column) => {
        const clipIds = row.cells[column] ?? [];
        return (
          <div className="coverage-matrix__cell" key={column}>
            {clipIds.length > 0 ? (
              <div className="coverage-matrix__chips">
                {clipIds.map((clipId) => (
                  <TakeChip key={clipId} clipId={clipId} circled={circledClipIds.has(clipId)} />
                ))}
              </div>
            ) : (
              <GapCell column={column} row={row} sql={sql} />
            )}
          </div>
        );
      })}
      <div
        className={isGap ? "coverage-matrix__status coverage-matrix__status--gap mono" : "coverage-matrix__status mono"}
        title={statusHoverText(row, sql)}
      >
        {row.status}
      </div>
    </div>
  );
}

export function CoveragePage() {
  const [matrix, setMatrix] = useState<CoverageMatrix | null>(null);
  const [error, setError] = useState(false);
  const [circledClipIds, setCircledClipIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    getCoverageMatrix().then((m) => {
      if (cancelled) return;
      if (!m) {
        setError(true);
        return;
      }
      setMatrix(m);
    });
    getClipList().then((clips) => {
      if (!cancelled) setCircledClipIds(new Set(clips.filter((c) => c.circled).map((c) => c.clip_id)));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const columns = matrix?.columns ?? [];

  return (
    <Shell
      topBarRight={
        <div className="coverage-page__actions">
          <button type="button" className="coverage-page__btn" onClick={() => window.print()}>
            Export as PDF
          </button>
          <Link to="/shot-list" className="coverage-page__btn coverage-page__btn--primary">
            Send gaps to shot list
          </Link>
        </div>
      }
    >
      <div className="coverage-page">
        {error && <p className="coverage-page__error">Could not load the coverage grid.</p>}
        {matrix && (
          <>
            <div className="coverage-page__header">
              <div className="coverage-page__heading">
                <div className="coverage-page__overline mono">COVERAGE</div>
                <h1 className="coverage-page__headline">{matrix.headline}</h1>
              </div>
              <div className="coverage-page__stats">
                <div className="coverage-page__stat">
                  <div className="coverage-page__stat-caption mono">TAKES PRINTED</div>
                  <div className="coverage-page__stat-value mono">{matrix.stats.takes_printed}</div>
                </div>
                <div className="coverage-page__stat">
                  <div className="coverage-page__stat-caption mono">SCENES</div>
                  <div className="coverage-page__stat-value mono">{matrix.stats.scenes}</div>
                </div>
                <div className="coverage-page__stat">
                  <div className="coverage-page__stat-caption mono">GAPS FLAGGED</div>
                  <div className="coverage-page__stat-value coverage-page__stat-value--accent mono">
                    {matrix.stats.gaps_flagged}
                  </div>
                </div>
              </div>
            </div>

            <div className="coverage-matrix" role="table">
              <div className="coverage-matrix__row coverage-matrix__row--header" role="row">
                <span>SCENE / SLATE</span>
                {columns.map((column) => (
                  <span key={column}>{column}</span>
                ))}
                <span className="coverage-matrix__status-header">STATUS</span>
              </div>
              {matrix.rows.map((row) => (
                <MatrixRow
                  key={`${row.scene}-${row.slate}`}
                  row={row}
                  columns={columns}
                  sql={matrix.sql}
                  circledClipIds={circledClipIds}
                />
              ))}
            </div>

            <div className="coverage-legend">
              <div className="coverage-legend__item">
                <span className="coverage-legend__swatch coverage-legend__swatch--printed" />
                PRINTED TAKE
              </div>
              <div className="coverage-legend__item">
                <span className="coverage-legend__swatch coverage-legend__swatch--circled" />
                CIRCLED
              </div>
              <div className="coverage-legend__item">
                <span className="coverage-legend__swatch coverage-legend__swatch--not-shot" />
                NOT SHOT
              </div>
              <div className="coverage-legend__spacer" />
              <div className="coverage-legend__note">
                Derived from a single aggregate over{" "}
                <span className="mono coverage-legend__code">visuals.shot_type</span> — not a hand-kept list.
              </div>
            </div>
          </>
        )}
      </div>
    </Shell>
  );
}
