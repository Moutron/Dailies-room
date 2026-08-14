import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getClipList, getPosterUrl, getStats, searchClips } from "../api";
import { formatDuration, formatTRT, shotTypeLabel } from "../agentCopy";
import { SHOT_TYPE_BUCKETS, reelCounts, toggleParam } from "../reels";
import { Shell } from "../shell/Shell";
import type { ClipListItem, IndexStats, SearchHit, SearchResponse } from "../types";

type Mode = "semantic" | "keyword";

function ModeToggle({ mode, onToggle }: { mode: Mode; onToggle: () => void }) {
  return (
    <button type="button" className="reels-search__mode mono" onClick={onToggle}>
      {mode === "semantic" ? "SEMANTIC" : "KEYWORD"}
    </button>
  );
}

function SearchBar({
  value,
  onChange,
  onSubmit,
  mode,
  onToggleMode,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  mode: Mode;
  onToggleMode: () => void;
}) {
  return (
    <form
      className="reels-search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <span className="reels-search__icon mono" aria-hidden="true">
        ⌕
      </span>
      <input
        className="reels-search__input"
        type="text"
        placeholder="Search dialogue and visuals…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Search"
      />
      <ModeToggle mode={mode} onToggle={onToggleMode} />
    </form>
  );
}

function ScoreBadge({ score }: { score: number }) {
  return <span className="reels-card__score mono">{score.toFixed(2)}</span>;
}

function ResultCard({ hit, isTop }: { hit: SearchHit; isTop: boolean }) {
  return (
    <Link
      to={`/clip/${encodeURIComponent(hit.clip_id)}`}
      className={isTop ? "reels-card reels-card--top" : "reels-card"}
    >
      <div className="reels-card__thumb" style={{ backgroundImage: `url(${getPosterUrl(hit.clip_id)})` }}>
        {hit.score != null && <ScoreBadge score={hit.score} />}
      </div>
      <div className="reels-card__body">
        <div className={isTop ? "reels-card__quote reels-card__quote--top" : "reels-card__quote"}>
          “{hit.quote}”
        </div>
        <div className="reels-card__meta mono">
          {hit.speaker && (
            <>
              <span className={isTop ? "reels-card__speaker reels-card__speaker--top" : "reels-card__speaker"}>
                {hit.speaker}
              </span>
              <span className="reels-card__meta-sep">·</span>
            </>
          )}
          <span>{hit.clip_id}</span>
          {hit.timecode_in && (
            <>
              <span className="reels-card__meta-sep">·</span>
              <span>{hit.timecode_in}</span>
            </>
          )}
        </div>
        <div className="reels-card__spacer" />
        {hit.note && (
          <div className="reels-card__note-row">
            <span className={isTop ? "reels-card__pill reels-card__pill--top mono" : "reels-card__pill mono"}>
              {hit.note}
            </span>
            <span className="reels-card__note-label mono">{hit.note_label}</span>
          </div>
        )}
      </div>
    </Link>
  );
}

function searchOverline(result: SearchResponse): string {
  const n = result.hits.length;
  const noun = `${n} MATCH${n === 1 ? "" : "ES"}`;
  return result.mode === "semantic" ? `${noun} BY MEANING · NOT BY KEYWORD` : `${noun} BY KEYWORD`;
}

function searchNote(mode: Mode): string {
  return mode === "semantic"
    ? "Vector search over the dialogue and visual embeddings Gemini wrote at ingest, ranked in ClickHouse."
    : "Substring match over dialogue and visual descriptions — no ranking, no meaning.";
}

function ContactTile({ clip }: { clip: ClipListItem }) {
  return (
    <Link
      to={`/clip/${encodeURIComponent(clip.clip_id)}`}
      className={clip.circled ? "reels-tile reels-tile--circled" : "reels-tile"}
    >
      <div className="reels-tile__thumb" style={{ backgroundImage: `url(${getPosterUrl(clip.clip_id)})` }} />
      <div className="reels-tile__info">
        <span className="reels-tile__id mono">
          {clip.clip_id}
          {clip.circled && <span className="reels-tile__star"> ★</span>}
        </span>
        <span className="reels-tile__sub mono">
          {shotTypeLabel(clip.shot_type ?? undefined)} · {formatDuration(clip.duration_s)}
        </span>
      </div>
    </Link>
  );
}

function FilterCheckbox({
  label,
  checked,
  onToggle,
  disabled,
  title,
  count,
}: {
  label: string;
  checked: boolean;
  onToggle?: () => void;
  disabled?: boolean;
  title?: string;
  count?: number;
}) {
  return (
    <label
      className={disabled ? "left-rail__filter-item left-rail__filter-item--disabled" : "left-rail__filter-item"}
      title={title}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={onToggle}
        className="left-rail__filter-input"
      />
      <span className={checked ? "left-rail__checkbox left-rail__checkbox--checked" : "left-rail__checkbox"}>
        {checked && "✓"}
      </span>
      <span className="left-rail__filter-label">{label}</span>
      {count != null && <span className="left-rail__filter-count mono">{count}</span>}
    </label>
  );
}

export function ReelsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const reelFilters = searchParams.getAll("reel");
  const shotFilters = searchParams.getAll("shot_type");
  const circledOnly = searchParams.get("circled") === "1";

  const [allClips, setAllClips] = useState<ClipListItem[]>([]);
  const [clips, setClips] = useState<ClipListItem[]>([]);
  const [stats, setStats] = useState<IndexStats | null>(null);

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("semantic");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);

  // The unfiltered list drives the rail's real per-reel counts.
  useEffect(() => {
    getClipList().then(setAllClips);
    getStats().then(setStats);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getClipList(reelFilters, shotFilters).then((c) => {
      if (!cancelled) setClips(c);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.toString()]);

  function runSearch(q: string, m: Mode) {
    if (!q.trim()) {
      setResult(null);
      return;
    }
    setSearching(true);
    searchClips(q, m)
      .then(setResult)
      .finally(() => setSearching(false));
  }

  function toggleReel(reel: string) {
    setSearchParams(toggleParam(searchParams, "reel", reel));
  }

  function toggleShotType(bucket: string) {
    setSearchParams(toggleParam(searchParams, "shot_type", bucket));
  }

  function toggleCircledOnly() {
    const next = new URLSearchParams(searchParams);
    if (circledOnly) next.delete("circled");
    else next.set("circled", "1");
    setSearchParams(next);
  }

  function toggleMode() {
    const next: Mode = mode === "semantic" ? "keyword" : "semantic";
    setMode(next);
    if (query.trim()) runSearch(query, next);
  }

  const filters = (
    <>
      <div className="left-rail__label mono">FILTER</div>
      <div className="left-rail__filter-list">
        <FilterCheckbox label="Circled takes only" checked={circledOnly} onToggle={toggleCircledOnly} />
      </div>
      <div className="left-rail__divider" role="presentation" />
      <div className="left-rail__label mono">REEL</div>
      <div className="left-rail__filter-list">
        {reelCounts(allClips).map(({ reel, count }) => (
          <FilterCheckbox
            key={reel}
            label={reel}
            count={count}
            checked={reelFilters.includes(reel)}
            onToggle={() => toggleReel(reel)}
          />
        ))}
      </div>
      <div className="left-rail__divider" role="presentation" />
      <div className="left-rail__label mono">SHOT TYPE</div>
      <div className="left-rail__filter-list">
        {SHOT_TYPE_BUCKETS.map((bucket) => (
          <FilterCheckbox
            key={bucket}
            label={bucket}
            checked={shotFilters.includes(bucket)}
            onToggle={() => toggleShotType(bucket)}
          />
        ))}
      </div>
    </>
  );

  return (
    <Shell
      filters={filters}
      topBarRight={
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={() => runSearch(query, mode)}
          mode={mode}
          onToggleMode={toggleMode}
        />
      }
    >
      <div className="reels-page">
        {result && (
          <>
            <div className="reels-page__header">
              <div className="reels-page__heading">
                <div className="reels-page__overline mono">{searchOverline(result)}</div>
                <h1 className="reels-page__headline">“{result.query}”</h1>
              </div>
              <div className="reels-page__spacer" />
              <div className="reels-page__note">{searchNote(mode)}</div>
            </div>

            {searching ? (
              <p className="reels-page__status mono">Searching…</p>
            ) : result.hits.length === 0 ? (
              <p className="reels-page__status mono">No matches for “{result.query}.”</p>
            ) : (
              <div className="reels-cards">
                {result.hits.map((hit, i) => (
                  <ResultCard key={`${hit.kind}-${hit.clip_id}-${hit.timecode_in}-${i}`} hit={hit} isTop={i === 0} />
                ))}
              </div>
            )}

            <div className="reels-page__divider" />
          </>
        )}

        <div className="reels-page__section-header">
          <span className="reels-page__section-label mono">EVERYTHING FROM TODAY</span>
          {stats && (
            <span className="reels-page__section-stats">
              {stats.clip_count} clips · {formatTRT(stats.total_duration_s)}
            </span>
          )}
        </div>
        <div className="reels-grid">
          {(circledOnly ? clips.filter((c) => c.circled) : clips).map((clip) => (
            <ContactTile key={clip.clip_id} clip={clip} />
          ))}
        </div>
      </div>
    </Shell>
  );
}
