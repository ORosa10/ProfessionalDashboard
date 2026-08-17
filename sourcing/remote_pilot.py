"""Remote-work sourcing (workstream D).

Pulls remote roles from public remote-board feeds (Remote OK, Remotive,
We Work Remotely), keeps only finance/treasury/risk/investment-relevant ones,
and writes them to data/jobs_remote_staging.csv in the same schema as the
sector staging files. No company layer: these come from boards, not the
Company Universe. Deterministic; designed to run in GitHub Actions.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]

try:  # reuse the coarse keyword pre-filter score from workstream C
    from sourcing.big4_pilot import calibrate_jobs
except Exception:  # pragma: no cover - keep sourcing resilient if imports fail
    calibrate_jobs = None

STAGING_COLUMNS = [
    "job_id", "canonical_company_id", "company", "title", "description",
    "description_en", "translation_status", "market", "location",
    "priority_locations", "job_url", "source_url", "source_id", "date_posted",
    "discovered_at", "last_seen_at", "relevance_score", "matched_terms",
    "verification", "status", "alternate_job_urls", "duplicate_count",
    "calibration_score", "calibration_note",
]

FINANCE_TERMS = [
    "treasury", "risk", "derivative", "valuation", " fx ", "foreign exchange",
    "interest rate", "liquidity", "commodit", "investment", "portfolio",
    "corporate finance", "financial model", "quant", "capital markets",
    "hedging", "fixed income", "financial analyst", "m&a", "fp&a",
]

UA = {"User-Agent": "Mozilla/5.0 ProfessionalDashboard/1.0"}


def _clean(text: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", str(text or "")))).strip()


def _relevant(title: str, desc: str) -> list[str]:
    text = f" {title} {desc} ".lower()
    return [t.strip() for t in FINANCE_TERMS if t in text]


def fetch_remoteok() -> list[tuple]:
    out = []
    try:
        r = requests.get("https://remoteok.com/api", headers=UA, timeout=30)
        r.raise_for_status()
        for item in r.json():
            if not isinstance(item, dict) or not item.get("position"):
                continue
            out.append((_clean(item.get("position")), _clean(item.get("company")),
                        _clean(item.get("description")), item.get("url", ""),
                        "remoteok", str(item.get("date", ""))))
    except Exception as exc:
        print("remoteok failed:", exc)
    return out


def fetch_remotive() -> list[tuple]:
    out = []
    try:
        r = requests.get("https://remotive.com/api/remote-jobs", headers=UA, timeout=30)
        r.raise_for_status()
        for item in r.json().get("jobs", []):
            out.append((_clean(item.get("title")), _clean(item.get("company_name")),
                        _clean(item.get("description")), item.get("url", ""),
                        "remotive", str(item.get("publication_date", ""))))
    except Exception as exc:
        print("remotive failed:", exc)
    return out


def fetch_wwr() -> list[tuple]:
    out = []
    for feed in ["https://weworkremotely.com/categories/remote-finance-and-legal-jobs.rss"]:
        try:
            r = requests.get(feed, headers=UA, timeout=30)
            r.raise_for_status()
            for it in ET.fromstring(r.content).iter("item"):
                title = _clean(it.findtext("title"))
                company, role = "", title
                if ":" in title:
                    company, role = [p.strip() for p in title.split(":", 1)]
                out.append((role, company, _clean(it.findtext("description")),
                            _clean(it.findtext("link")), "weworkremotely",
                            _clean(it.findtext("pubDate"))))
        except Exception as exc:
            print("wwr failed:", feed, exc)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "jobs_remote_staging.csv"))
    args = ap.parse_args()
    now = datetime.now(timezone.utc).isoformat()

    raw = fetch_remoteok() + fetch_remotive() + fetch_wwr()
    print(f"fetched {len(raw)} raw remote roles")
    recs = []
    for title, company, desc, url, src, posted in raw:
        if not title or not url:
            continue
        hits = _relevant(title, desc)
        if not hits:
            continue
        recs.append({
            "job_id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
            "canonical_company_id": "", "company": company or src.title(),
            "title": title, "description": desc, "description_en": desc,
            "translation_status": "assumed_en", "market": "Remote",
            "location": "Remote", "priority_locations": "Remote",
            "job_url": url, "source_url": url, "source_id": src,
            "date_posted": posted, "discovered_at": now, "last_seen_at": now,
            "relevance_score": len(hits), "matched_terms": "; ".join(hits),
            "verification": "board_listing", "status": "Open",
            "alternate_job_urls": "", "duplicate_count": 0,
            "calibration_score": "", "calibration_note": "",
        })

    df = pd.DataFrame(recs)
    if df.empty:
        print("no relevant remote roles found")
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
    print(f"wrote {len(df)} remote roles to {args.out}")


if __name__ == "__main__":
    main()
