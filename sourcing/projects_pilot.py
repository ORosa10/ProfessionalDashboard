"""Projects / Interim sourcing (workstream E).

Paid project / interim / contract / freelance finance work for Ondrej
personally. Reuses the remote-board fetchers from remote_pilot but keeps only
project-type roles (contract/interim/freelance/fixed-term) in the finance
domain, regardless of location (that's E's axis; D=Remote keeps permanent).
Public tenders (TED / Vestnik, CPV finance) are a planned second channel.
Deterministic; runs in GitHub Actions.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sourcing.remote_pilot import (
    STAGING_COLUMNS, fetch_remoteok, fetch_remotive, fetch_wwr,
    _relevant, is_project_role,
)

try:
    from sourcing.big4_pilot import calibrate_jobs
except Exception:
    calibrate_jobs = None

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "jobs_projects_staging.csv"))
    args = ap.parse_args()
    now = datetime.now(timezone.utc).isoformat()

    ro, rv, ww = fetch_remoteok(), fetch_remotive(), fetch_wwr()
    print(f"raw fetched: remoteok={len(ro)} remotive={len(rv)} wwr={len(ww)}")
    raw = ro + rv + ww
    recs = []
    for title, company, desc, url, src, posted, meta in raw:
        if not title or not url:
            continue
        hits = _relevant(title, meta)
        if not hits:
            continue
        if not is_project_role(title, desc):
            continue  # E keeps ONLY project/interim/contract roles
        recs.append({
            "job_id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
            "canonical_company_id": "", "company": company or src.title(),
            "title": title, "description": desc, "description_en": desc,
            "translation_status": "assumed_en", "market": "Project / Interim",
            "location": "Project / Interim", "priority_locations": "",
            "job_url": url, "source_url": url, "source_id": src,
            "date_posted": posted, "discovered_at": now, "last_seen_at": now,
            "relevance_score": len(hits), "matched_terms": "; ".join(hits),
            "verification": "board_listing", "status": "Open",
            "alternate_job_urls": "", "duplicate_count": 0,
            "calibration_score": "", "calibration_note": "",
        })

    df = pd.DataFrame(recs)
    if df.empty:
        print("no project/interim finance roles found")
        df = pd.DataFrame(columns=STAGING_COLUMNS)
    else:
        df = df.drop_duplicates("job_id", keep="first")
        if calibrate_jobs is not None:
            try:
                df = calibrate_jobs(df)
            except Exception as exc:
                print("calibrate_jobs skipped:", exc)
    df = df.reindex(columns=STAGING_COLUMNS, fill_value="")
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} project/interim roles to {args.out}")


if __name__ == "__main__":
    main()
