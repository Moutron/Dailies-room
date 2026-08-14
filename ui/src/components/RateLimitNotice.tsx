/** The muted-grey inline notice for a 429 — an expected condition (burst of
 * 5, then ~20/min), never a modal or a red toast. The retry window is the
 * server's real Retry-After header, not a made-up "try again soon". */
export function RateLimitNotice({ retryAfterSeconds }: { retryAfterSeconds: number }) {
  return (
    <div className="rate-limit-notice" role="status">
      Too many requests — try again in {retryAfterSeconds}s.
    </div>
  );
}
