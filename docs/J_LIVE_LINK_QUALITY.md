# J live-link quality contract

This gate protects the live J shortlist from stale vacancies without turning transient website failures into hard exclusions.

## Evidence hierarchy

1. A vacancy seen again by a current board/company source within 48 hours is `live`.
2. Otherwise, a recent cached verification may be reused.
3. Older vacancies are revalidated by HTTP GET.

## Hard dead signals

Only high-confidence evidence removes a role from J automatically:
- HTTP 404 or 410;
- an explicit vacancy-expired / no-longer-available marker on the returned page.

The exclusion reason is stored as `link_quality:<evidence>` in `data/j_live_excluded.csv`.

## Non-hard failures

403, 429, timeouts, WAFs, 5xx responses, missing URLs, and other technical failures are `verification_failed` and remain in J. A redirect from a job-detail URL to a generic career page is `likely_dead`, not an automatic exclusion, because some ATS platforms canonicalize detail URLs this way.

## Persistence

`data/j_link_verification.csv` is the canonical latest link-verification state by opportunity. Live J rows expose `link_status`, `last_verified_at`, and `verification_evidence`.

## Cadence

- Every production C→J promotion revalidates the preliminary J pool before publication.
- `J live-link quality` runs daily against the current live J pool so a vacancy can be removed even when no new C promotion occurs.
