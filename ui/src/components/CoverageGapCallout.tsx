import { Link } from "react-router-dom";
import { describeGap } from "../agentCopy";
import type { ResultRow } from "../types";

/** The payoff — a real gap, generated from get_coverage's gap fields on the
 * first row. Renders nothing when the tool returned no gap; never a
 * fabricated "all good" state either. */
export function CoverageGapCallout({ row }: { row: ResultRow }) {
  const body = describeGap(row);
  if (!body) return null;

  return (
    <div className="coverage-gap">
      <div className="coverage-gap__label">
        <span className="coverage-gap__marker" aria-hidden="true" />
        COVERAGE GAP
      </div>
      <p className="coverage-gap__body">{body}</p>
      <div className="coverage-gap__actions">
        <Link
          to="/shot-list"
          className="coverage-gap__action coverage-gap__action--primary"
          title="Opens the real shot list — generated from today's coverage aggregate, not from this specific gap."
        >
          Add to shot list
        </Link>
        <Link to="/coverage" className="coverage-gap__action coverage-gap__action--secondary">
          Open coverage grid
        </Link>
      </div>
    </div>
  );
}
