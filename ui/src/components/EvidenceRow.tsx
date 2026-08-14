import type { QueryEvidence } from "../types";

/** The row count is highlighted violet only when it's zero — the honesty
 * beat's whole point (`dialogue · 0 rows`), never dressed up for a normal
 * non-zero result. */
function Segment({ e }: { e: QueryEvidence }) {
  if (e.error) return <span>{e.table} · error</span>;
  const n = e.row_count ?? 0;
  return (
    <span>
      {e.table} · <span className={n === 0 ? "evidence-row__zero" : undefined}>{n} row{n === 1 ? "" : "s"}</span>
    </span>
  );
}

/** The visible proof an answer came from a query — real table names, real
 * row counts, real elapsed time, real SQL. Renders nothing until evidence
 * has actually arrived; never a placeholder claiming a query ran. */
export function EvidenceRow({ evidence }: { evidence: QueryEvidence[] }) {
  if (evidence.length === 0) return null;

  const totalMs = evidence.reduce((sum, e) => sum + e.elapsed_ms, 0);

  return (
    <details className="evidence-row">
      <summary>
        <span className="evidence-row__label">EVIDENCE</span>
        {evidence.map((e, i) => (
          <span key={i}>
            <Segment e={e} />
            {i < evidence.length - 1 && <span className="evidence-row__sep">|</span>}
          </span>
        ))}
        <span>{(totalMs / 1000).toFixed(2)}s</span>
        <span className="evidence-row__toggle">show query</span>
      </summary>
      <div className="evidence-row__queries">
        {evidence.map((e, i) => (
          <pre key={i} className="evidence-row__sql mono">
            {e.sql}
            {e.error && `\n-- error: ${e.error}`}
          </pre>
        ))}
      </div>
    </details>
  );
}
