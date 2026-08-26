from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

VERIFICATION_COLUMNS = [
    "opportunity_id",
    "job_url",
    "link_status",
    "last_verified_at",
    "http_status",
    "final_url",
    "verification_evidence",
    "verification_error",
]

DEAD_PHRASES = (
    "job is no longer available",
    "job no longer available",
    "position is no longer available",
    "position has been filled",
    "job has expired",
    "vacancy has expired",
    "this job is closed",
    "no longer accepting applications",
    "stellenangebot ist nicht mehr verfügbar",
    "stelle ist nicht mehr verfügbar",
    "position wurde besetzt",
    "stelle wurde besetzt",
    "bewerbungsfrist abgelaufen",
    "pozice již není dostupná",
    "pozice uz není dostupná",
    "nabídka již není aktuální",
    "nabidka jiz neni aktualni",
    "pozice byla obsazena",
    "inzerát již není aktivní",
    "inzerat jiz neni aktivni",
    "stillingen er ikke lenger tilgjengelig",
    "stillingen er besatt",
    "stillingen er ikke længere tilgængelig",
    "jobbet är inte längre tillgängligt",
    "tjänsten är inte längre tillgänglig",
    "työpaikka ei ole enää haettavissa",
)

GENERIC_CAREER_PATH = re.compile(
    r"^/(?:careers?|jobs?|vacancies|opportunities|search(?:-results)?)/?$",
    re.IGNORECASE,
)
JOBISH_PATH = re.compile(r"(?:/job/|/jobs/|/vacan|/position|/stellen|/career).*?(?:\d{3,}|[-_/][a-z0-9]{6,})", re.IGNORECASE)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.8",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, utc=True, errors="raise")
        return parsed.to_pydatetime()
    except Exception:
        return None


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _dead_phrase(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).lower()
    return next((phrase for phrase in DEAD_PHRASES if phrase in normalized), "")


def _generic_redirect(original_url: str, final_url: str) -> bool:
    if not original_url or not final_url or original_url == final_url:
        return False
    original = urlparse(original_url)
    final = urlparse(final_url)
    if original.netloc.lower() != final.netloc.lower():
        return False
    if not JOBISH_PATH.search(original.path):
        return False
    return bool(GENERIC_CAREER_PATH.fullmatch(final.path or "/")) and not final.query


def classify_response(
    status_code: int,
    original_url: str,
    final_url: str,
    body: str,
) -> tuple[str, str]:
    if status_code in {404, 410}:
        return "dead", f"http_{status_code}"
    if status_code in {401, 403, 408, 425, 429} or status_code >= 500:
        return "verification_failed", f"http_{status_code}"
    if 200 <= status_code < 300:
        phrase = _dead_phrase(body)
        if phrase:
            return "dead", f"expired_marker:{phrase}"
        if _generic_redirect(original_url, final_url):
            # Strong warning, but not a hard exclusion: some ATSs intentionally
            # canonicalize detail URLs to a rendered search page.
            return "likely_dead", "redirected_to_generic_careers"
        return "live", f"http_{status_code}"
    return "verification_failed", f"http_{status_code}"


def _verification_record(
    opportunity_id: str,
    job_url: str,
    status: str,
    verified_at: str,
    http_status: object = "",
    final_url: str = "",
    evidence: str = "",
    error: str = "",
) -> dict[str, str]:
    return {
        "opportunity_id": opportunity_id,
        "job_url": job_url,
        "link_status": status,
        "last_verified_at": verified_at,
        "http_status": str(http_status or ""),
        "final_url": final_url,
        "verification_evidence": evidence,
        "verification_error": error,
    }


def _http_verify(row: dict, timeout: float) -> dict[str, str]:
    opportunity_id = str(row.get("opportunity_id") or row.get("job_id") or "").strip()
    job_url = str(row.get("job_url") or "").strip()
    checked_at = _now().isoformat()
    if not job_url:
        return _verification_record(
            opportunity_id,
            job_url,
            "verification_failed",
            checked_at,
            evidence="missing_job_url",
        )
    try:
        response = requests.get(job_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        body = response.text[:250_000]
        status, evidence = classify_response(response.status_code, job_url, response.url, body)
        return _verification_record(
            opportunity_id,
            job_url,
            status,
            checked_at,
            http_status=response.status_code,
            final_url=response.url,
            evidence=evidence,
        )
    except requests.RequestException as exc:
        return _verification_record(
            opportunity_id,
            job_url,
            "verification_failed",
            checked_at,
            evidence="request_error",
            error=type(exc).__name__,
        )


def verify_pool(
    pool: pd.DataFrame,
    cache: pd.DataFrame | None = None,
    *,
    source_recent_hours: float = 48,
    cache_hours: float = 24,
    max_workers: int = 8,
    timeout: float = 12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if pool.empty:
        return pool.copy(), pd.DataFrame(columns=VERIFICATION_COLUMNS)

    jobs = pool.fillna("").copy()
    if "opportunity_id" not in jobs.columns:
        jobs["opportunity_id"] = jobs.get("job_id", "")
    if "job_url" not in jobs.columns:
        jobs["job_url"] = ""
    if "last_seen_at" not in jobs.columns:
        jobs["last_seen_at"] = ""

    existing: dict[str, dict] = {}
    if cache is not None and not cache.empty and "opportunity_id" in cache.columns:
        deduped = cache.fillna("").drop_duplicates("opportunity_id", keep="last")
        existing = {str(row["opportunity_id"]): row.to_dict() for _, row in deduped.iterrows()}

    now = _now()
    source_cutoff = now - timedelta(hours=source_recent_hours)
    cache_cutoff = now - timedelta(hours=cache_hours)
    records: dict[str, dict[str, str]] = {}
    pending: list[dict] = []

    for row in jobs.to_dict("records"):
        opportunity_id = str(row.get("opportunity_id") or row.get("job_id") or "").strip()
        job_url = str(row.get("job_url") or "").strip()
        last_seen = _parse_dt(row.get("last_seen_at"))
        if last_seen and last_seen >= source_cutoff:
            records[opportunity_id] = _verification_record(
                opportunity_id,
                job_url,
                "live",
                last_seen.isoformat(),
                final_url=job_url,
                evidence="source_seen_recently",
            )
            continue

        cached = existing.get(opportunity_id, {})
        cached_at = _parse_dt(cached.get("last_verified_at"))
        same_url = str(cached.get("job_url") or "").strip() == job_url
        cached_status = str(cached.get("link_status") or "").strip()
        if same_url and cached_at and cached_at >= cache_cutoff and cached_status in {"live", "dead", "likely_dead"}:
            records[opportunity_id] = {col: str(cached.get(col, "")) for col in VERIFICATION_COLUMNS}
            continue
        pending.append(row)

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as executor:
            futures = {executor.submit(_http_verify, row, timeout): row for row in pending}
            for future in as_completed(futures):
                row = futures[future]
                opportunity_id = str(row.get("opportunity_id") or row.get("job_id") or "").strip()
                try:
                    records[opportunity_id] = future.result()
                except Exception as exc:  # defensive: one URL must never fail the batch
                    records[opportunity_id] = _verification_record(
                        opportunity_id,
                        str(row.get("job_url") or ""),
                        "verification_failed",
                        _now().isoformat(),
                        evidence="worker_error",
                        error=type(exc).__name__,
                    )

    verification = pd.DataFrame(records.values()).reindex(columns=VERIFICATION_COLUMNS, fill_value="")
    return jobs, verification


def apply_verification(
    pool: pd.DataFrame,
    excluded: pd.DataFrame,
    verification: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    jobs = pool.fillna("").copy()
    if "opportunity_id" not in jobs.columns:
        jobs["opportunity_id"] = jobs.get("job_id", "")
    if verification.empty:
        jobs["link_status"] = "verification_failed"
        jobs["last_verified_at"] = ""
        jobs["verification_evidence"] = "no_verification_record"
        return jobs, excluded.copy()

    verify = verification.fillna("").drop_duplicates("opportunity_id", keep="last")
    verify_map = {str(row["opportunity_id"]): row.to_dict() for _, row in verify.iterrows()}
    jobs["link_status"] = jobs["opportunity_id"].map(lambda oid: str(verify_map.get(str(oid), {}).get("link_status", "verification_failed")))
    jobs["last_verified_at"] = jobs["opportunity_id"].map(lambda oid: str(verify_map.get(str(oid), {}).get("last_verified_at", "")))
    jobs["verification_evidence"] = jobs["opportunity_id"].map(lambda oid: str(verify_map.get(str(oid), {}).get("verification_evidence", "")))

    dead = jobs["link_status"].eq("dead")
    new_excluded = jobs.loc[dead, ["opportunity_id", "company", "title"]].copy()
    if not new_excluded.empty:
        new_excluded["excluded_reason"] = jobs.loc[dead, "opportunity_id"].map(
            lambda oid: "link_quality:" + str(verify_map.get(str(oid), {}).get("verification_evidence", "dead"))
        ).values

    kept = jobs.loc[~dead].reset_index(drop=True)
    prior = excluded.fillna("").copy() if excluded is not None else pd.DataFrame()
    combined = pd.concat([prior, new_excluded], ignore_index=True, sort=False)
    if not combined.empty and "opportunity_id" in combined.columns:
        combined = combined.drop_duplicates(["opportunity_id", "excluded_reason"], keep="last")
    return kept, combined


def merge_cache(previous: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if previous is not None and not previous.empty:
        frames.append(previous.reindex(columns=VERIFICATION_COLUMNS, fill_value=""))
    if current is not None and not current.empty:
        frames.append(current.reindex(columns=VERIFICATION_COLUMNS, fill_value=""))
    if not frames:
        return pd.DataFrame(columns=VERIFICATION_COLUMNS)
    merged = pd.concat(frames, ignore_index=True).fillna("")
    return merged.drop_duplicates("opportunity_id", keep="last").reindex(columns=VERIFICATION_COLUMNS, fill_value="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Revalidate live J links without treating WAF/timeouts as dead vacancies")
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--excluded", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--out-pool", required=True, type=Path)
    parser.add_argument("--out-excluded", required=True, type=Path)
    parser.add_argument("--out-cache", required=True, type=Path)
    parser.add_argument("--source-recent-hours", type=float, default=48)
    parser.add_argument("--cache-hours", type=float, default=24)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args()

    pool = _read(args.pool)
    excluded = _read(args.excluded)
    previous_cache = _read(args.cache)
    normalized_pool, current = verify_pool(
        pool,
        previous_cache,
        source_recent_hours=args.source_recent_hours,
        cache_hours=args.cache_hours,
        max_workers=args.max_workers,
        timeout=args.timeout,
    )
    final_pool, final_excluded = apply_verification(normalized_pool, excluded, current)
    cache = merge_cache(previous_cache, current)

    for path in (args.out_pool, args.out_excluded, args.out_cache):
        path.parent.mkdir(parents=True, exist_ok=True)
    final_pool.to_csv(args.out_pool, index=False)
    final_excluded.to_csv(args.out_excluded, index=False)
    cache.to_csv(args.out_cache, index=False)

    counts = current["link_status"].value_counts().to_dict() if not current.empty else {}
    print(f"J link verification: {counts}; kept={len(final_pool)} excluded_dead={int((current.get('link_status', '') == 'dead').sum()) if len(current) else 0}")


if __name__ == "__main__":
    main()
