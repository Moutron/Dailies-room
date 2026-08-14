import { useEffect, useState } from "react";
import { getClipList, getStats } from "../api";
import { formatTRT } from "../agentCopy";
import { SessionView } from "../components/SessionView";
import { Viewer } from "../components/Viewer";
import { Shell } from "../shell/Shell";
import type { ActiveClip, ClipMeta, IndexStats, SessionTurn } from "../types";

function StatsReadout({ stats }: { stats: IndexStats | null }) {
  if (!stats) return null;
  return (
    <div className="stats-readout mono">
      <span className="stats-readout__dot" aria-hidden="true" />
      {stats.clip_count} CLIPS INDEXED · {formatTRT(stats.total_duration_s)} TRT
    </div>
  );
}

export function AskPage() {
  const [active, setActive] = useState<ActiveClip | null>(null);
  const [activeMeta, setActiveMeta] = useState<ClipMeta | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [sessionTurns, setSessionTurns] = useState<SessionTurn[]>([]);
  const [circledClipIds, setCircledClipIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    getStats().then((s) => {
      if (!cancelled) setStats(s);
    });
    getClipList().then((clips) => {
      if (!cancelled) setCircledClipIds(new Set(clips.filter((c) => c.circled).map((c) => c.clip_id)));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  function onSeek(clipId: string, seconds: number) {
    setActive((prev) => ({
      clipId,
      seekSeconds: seconds,
      nonce: (prev?.nonce ?? 0) + 1,
    }));
  }

  return (
    <Shell topBarRight={<StatsReadout stats={stats} />} sessionTurns={sessionTurns}>
      <div className="ask-page">
        <SessionView
          onSeek={onSeek}
          activeReel={activeMeta?.reel}
          onSessionChange={setSessionTurns}
          circledClipIds={circledClipIds}
        />
        <Viewer active={active} onMetaLoaded={setActiveMeta} />
      </div>
    </Shell>
  );
}
