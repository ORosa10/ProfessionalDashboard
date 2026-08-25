"""Projects / Interim sourcing (workstream E).

Channel 1 discovers explicit paid contract/interim/freelance finance roles from
the same public remote-board feeds used by D. E is a sourcing lane, not a fit
classifier: candidates still go through C and the same actionability layer.

Remote scope is preserved instead of being overwritten by the label
"Project / Interim". Temporary source failures preserve the last successful
snapshot for that source. Public tenders remain a future separate E channel.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sourcing.remote_pilot import (
    STAGING_COLUMNS,
    _relevant,
    fetch_remoteok,
    fetch_remotive,
    fetch_wwr,
    is_project_role,
    merge_remote_snapshot,
    remote_scope_hint,
)

try:
    from sourcing.big4_pilot import calibrate_jobs
except Exception:  # pragma: no cover
    calibrate_jobs = None

ROOT = Path(__file__).resolve().parents[1]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=STAGING_COLUMNS)


def _read_previous(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_frame()
    try:
        return pd.read_csv(path).fillna("").reindex(columns=STAGING_COLUMNS, fill_value="")
    except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
        return _empty_frame()


def _records_frame(records: list[dict]) -> pd.DataFrame:
    if not records:
        return _empty_frame()
    frame = pd.DataFrame(records).drop_duplicates("job_id", keep="first")
    if calibrate_jobs is not None:
        try:
            frame = calibrate_jobs(frame)
        except Exception as exc:
            print("calibrate_jobs skipped:", exc)
    return frame.reindex(columns=STAGING_COLUMNS, fill_value="").fillna("")


def build_project_records(raw: list[tuple], now: str) -> list[dict]:
    records: list[dict] = []
    for title, company, desc, url, src, posted, meta in raw:
        if not title or not url:
            continue
        hits = _relevant(title, meta, src)
        if not hits or not is_project_role(title, desc):
            continue
        location = remote_scope_hint(title, desc, meta)
        records.append({
            "job_id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
            "canonical_company_id": "",
            "company": company or src.title(),
            "title": title,
            "description": desc,
            "description_en": desc,
            "translation_status": "assumed_en",
            # Channel 1 is remote-project sourcing. Project/interim is carried by
            # the E source stream, not faked into the geography fields.
            "market": "Remote",
            "location": location,
            "priority_locations": location,
            "job_url": url,
            "source_url": url,
            "source_id": src,
            "date_posted": posted,
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": len(hits),
            "matched_terms": "; ".join(hits),
            "verification": "board_listing_project_channel",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "data" / "jobs_projects_staging.csv"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc).isoformat()

    remoteok, ok_remoteok = fetch_remoteok()
    remotive, ok_remotive = fetch_remotive()
    wwr, ok_wwr = fetch_wwr()
    successful_sources = {
        source for source, ok in [
            ("remoteok", ok_remoteok),
            ("remotive", ok_remotive),
            ("weworkremotely", ok_wwr),
        ] if ok
    }
    print(
        f"raw fetched: remoteok={len(remoteok)} remotive={len(remotive)} wwr={len(wwr)}; "
        f"healthy_sources={','.join(sorted(successful_sources)) or 'none'}"
    )

    out_path = Path(args.out)
    previous = _read_previous(out_path)
    if not successful_sources and previous.empty:
        raise RuntimeError("All project source feeds failed and no previous E snapshot exists")

    current = _records_frame(build_project_records(remoteok + remotive + wwr, now))
    result = merge_remote_snapshot(current, previous, successful_sources)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    print(f"wrote {len(result)} project/interim roles to {out_path}")


if __name__ == "__main__":
    main()
