from __future__ import annotations

import argparse
import html
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import pandas as pd
from bs4 import BeautifulSoup

from sourcing import big4_pilot as common


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "job_sources_pe.csv"
JOBS_PATH = ROOT / "data" / "jobs_pe_staging.csv"
RUNS_PATH = ROOT / "data" / "source_runs_pe_staging.csv"

TARGET_LOCATION_TERMS = (
    "czech", "prague", "praha", "brno",
    "germany", "deutschland", "munich", "münchen", "berlin", "frankfurt", "hamburg",
    "austria", "österreich", "vienna", "wien",
    "switzerland", "schweiz", "zurich", "zürich", "zug",
    "united kingdom", "uk", "london",
    "sweden", "stockholm", "denmark", "copenhagen", "norway", "oslo",
    "finland", "helsinki", "nordic", "europe", "emea", "remote",
)

PE_ROLE_TERMS = (
    "investment", "investor", "private equity", "private credit", "portfolio",
    "finance", "financial", "fund", "valuation", "transaction", "m&a",
    "capital", "strategy", "corporate development", "treasury", "fp&a",
    "risk", "performance", "analytics", "data analyst", "restructuring",
    "value creation", "operations", "associate", "analyst",
)

EXCLUDED_ROLE_TERMS = (
    "intern", "internship", "working student", "graduate programme",
    "reception", "office assistant", "human resources", "talent acquisition",
    "legal counsel", "executive assistant", "personal assistant",
)

# PE_TARGETING.md v0.1 (2026-08-13, first 20-role calibration). Never a hard
# exclude -- these only nudge calibration_score/calibration_note in
# apply_pe_hypothesis() below, same "downrank, don't delete" principle as the
# rest of the pipeline.
PE_PRIORITY_TERMS = ("investment analyst", "analyst, private equity", "investment team analyst")
PE_SECONDARY_PRIORITY_TERMS = ("treasury", "fund finance", "cfo")
PE_DOWNRANK_TERMS = {
    "real estate": ("PE hypothesis: Real Estate downranked (3/3 Pass in first calibration)", 20),
    "investor relations": ("PE hypothesis: Investor Relations downranked (explicit Pass)", 20),
    "digital infrastructure": ("PE hypothesis: Digital Infrastructure downranked", 12),
}
PE_LEGAL_TAX_TERMS = ("counsel", "lawyer", " tax ")


def apply_pe_hypothesis(jobs: pd.DataFrame) -> pd.DataFrame:
    """Nudge review order per PE_TARGETING.md without deleting any candidate.

    Downranked lanes stay visible, just lower in review order; the priority
    lanes (Investment Analyst first, Treasury/Fund Finance/CFO second) get
    boosted. calibration_note explains why so it's clear during review.
    """
    if jobs.empty or "title" not in jobs.columns:
        return jobs
    jobs = jobs.copy()
    for idx, row in jobs.iterrows():
        text = f" {common.searchable(str(row.get('title', '')))} "
        notes: list[str] = []
        delta = 0
        if any(term in text for term in PE_PRIORITY_TERMS):
            delta += 20
            notes.append("PE hypothesis: matches top-priority Investment Analyst lane")
        elif any(term in text for term in PE_SECONDARY_PRIORITY_TERMS):
            delta += 12
            notes.append("PE hypothesis: matches Treasury/Fund Finance/CFO priority lane")
        for term, (note, penalty) in PE_DOWNRANK_TERMS.items():
            if term in text:
                delta -= penalty
                notes.append(note)
        if any(term in text for term in PE_LEGAL_TAX_TERMS):
            delta -= 15
            notes.append("PE hypothesis: legal/tax specialism, not the target finance lane")
        if not notes:
            continue
        current_score = pd.to_numeric(row.get("calibration_score", ""), errors="coerce")
        current_score = 50 if pd.isna(current_score) else current_score
        jobs.at[idx, "calibration_score"] = max(0, min(100, current_score + delta))
        existing_note = str(row.get("calibration_note", "") or "")
        jobs.at[idx, "calibration_note"] = " | ".join(n for n in [existing_note, *notes] if n)
    return jobs


def relevant_pe_title(title: str) -> bool:
    value = common.searchable(title)
    return (
        any(term in value for term in PE_ROLE_TERMS)
        and not any(term in value for term in EXCLUDED_ROLE_TERMS)
        and common.is_real_job_title(title)
    )


def target_location(location: str) -> bool:
    value = common.searchable(location)
    return not value or any(common.searchable(term) in value for term in TARGET_LOCATION_TERMS)


def _source_with_domain(source: pd.Series) -> pd.Series:
    result = source.copy()
    if not str(result.get("allowed_domains", "")).strip():
        result["allowed_domains"] = urlparse(str(result.seed_url)).netloc
    return result


def discover_greenhouse(source: pd.Series, max_jobs: int = 160) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    jobs: dict[str, dict] = {}
    board = urlparse(source.seed_url).path.strip("/").split("/")[-1]
    records: list[dict] = []
    try:
        response = common.fetch(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        )
        records = response.json().get("jobs") or []
    except Exception as exc:
        errors.append(f"Greenhouse listing: {type(exc).__name__}: {exc}")

    candidates = [
        record for record in records
        if relevant_pe_title(str(record.get("title") or ""))
        and target_location(str((record.get("location") or {}).get("name") or ""))
    ][:max_jobs]
    for record in candidates:
        record_id = str(record.get("id") or "")
        description = BeautifulSoup(
            html.unescape(str(record.get("content") or "")), "html.parser"
        ).get_text(" ", strip=True)
        posting = {
            "@type": "JobPosting",
            "title": record.get("title"),
            "description": description,
            "datePosted": record.get("updated_at") or "",
            "jobLocation": {
                "@type": "Place",
                "address": (record.get("location") or {}).get("name") or "",
            },
            "identifier": {"value": record_id},
            "url": record.get("absolute_url") or source.seed_url,
            "_verification": "official Greenhouse vacancy API",
        }
        job = common.posting_to_job(posting, posting["url"], source, started)
        if job:
            jobs[job["job_id"]] = job

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": 1,
        "candidate_job_pages": len(candidates),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def discover_personio(source: pd.Series, max_jobs: int = 160) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    jobs: dict[str, dict] = {}
    records: list[ElementTree.Element] = []
    xml_url = source.seed_url.rstrip("/") + "/xml"
    try:
        response = common.fetch(xml_url)
        root = ElementTree.fromstring(response.content)
        records = list(root.findall(".//position"))
    except Exception as exc:
        errors.append(f"Personio listing: {type(exc).__name__}: {exc}")

    def value(record: ElementTree.Element, name: str) -> str:
        node = record.find(name)
        return common.normalize("" if node is None else "".join(node.itertext()))

    candidates = [
        record for record in records
        if relevant_pe_title(value(record, "name"))
        and target_location(" ".join([value(record, "office"), value(record, "subcompany")]))
    ][:max_jobs]
    for record in candidates:
        record_id = value(record, "id")
        details = " ".join(
            common.normalize(" ".join(node.itertext()))
            for node in record.findall(".//jobDescription")
        )
        location = " · ".join(
            part for part in [value(record, "office"), value(record, "subcompany")] if part
        )
        public_url = value(record, "url") or source.seed_url
        posting = {
            "@type": "JobPosting",
            "title": value(record, "name"),
            "description": details,
            "datePosted": value(record, "createdAt"),
            "jobLocation": {"@type": "Place", "address": location},
            "identifier": {"value": record_id},
            "url": public_url,
            "_verification": "official Personio vacancy feed",
        }
        job = common.posting_to_job(posting, public_url, source, started)
        if job:
            jobs[job["job_id"]] = job

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": 1,
        "candidate_job_pages": len(candidates),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def discover_source(source: pd.Series, max_pages: int) -> tuple[list[dict], dict]:
    adapter = str(source.get("adapter") or "generic").lower()
    if adapter == "greenhouse":
        return discover_greenhouse(source)
    if adapter == "personio":
        return discover_personio(source)
    if adapter == "workday":
        return common.discover_workday_jobs(source, max_pages=min(max_pages, 15))
    if adapter == "successfactors":
        host = urlparse(str(source.seed_url)).netloc.lower().split(":")[0]
        common.SUCCESSFACTORS_HOSTS = tuple(
            dict.fromkeys((*common.SUCCESSFACTORS_HOSTS, host))
        )
        return common.discover_successfactors_sitemap_jobs(source, max_jobs=120)
    return common.discover_jobs(_source_with_domain(source), max_pages=min(max_pages, 30))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--source-id", action="append", default=[])
    args = parser.parse_args()

    common.ACTIVE_JOBS_OUTPUT_PATH = JOBS_PATH
    sources = pd.read_csv(SOURCES_PATH).fillna("")
    sources = sources[sources["enabled"].astype(str).str.lower().eq("true")]
    if args.source_id:
        sources = sources[sources["source_id"].isin(args.source_id)]

    all_jobs: list[dict] = []
    runs: list[dict] = []
    for _, source in sources.iterrows():
        if not common.due_for_check(source, RUNS_PATH):
            continue
        jobs, run = discover_source(source, args.max_pages)
        all_jobs.extend(jobs)
        runs.append(run)
        time.sleep(0.15)

    discovered = pd.DataFrame(all_jobs)
    if not discovered.empty:
        discovered = discovered[
            discovered["title"].map(relevant_pe_title)
            & discovered["location"].map(target_location)
        ]
        discovered = common.deduplicate_jobs(discovered)
    translated = common.translate_descriptions(discovered)
    merged = common.merge_jobs(translated, base_path=JOBS_PATH)
    merged = apply_pe_hypothesis(merged).sort_values(
        ["calibration_score", "relevance_score", "last_seen_at"],
        ascending=[False, False, False],
    )
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(JOBS_PATH, index=False)

    run_df = pd.DataFrame(runs)
    if RUNS_PATH.exists():
        run_df = pd.concat([pd.read_csv(RUNS_PATH).fillna(""), run_df], ignore_index=True)
    run_df.tail(2000).to_csv(RUNS_PATH, index=False)
    print(
        f"Checked {len(sources)} PE sources; stored {len(merged)} verified roles "
        f"in separate PE staging."
    )


if __name__ == "__main__":
    main()
