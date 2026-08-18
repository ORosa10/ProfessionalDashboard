"""Workstream G: company-agnostic country / job-board sweep.

The first production adapters intentionally use sources that expose stable,
public job data: Sweden's JobSearch API and Germany's Bundesagentur job pages.
Results use the shared jobs schema and calibration rules from workstream C.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests
from bs4 import BeautifulSoup

from sourcing.big4_pilot import calibrate_jobs, translate_descriptions

ROOT = Path(__file__).resolve().parents[1]
BOARDS_PATH = ROOT / "data" / "job_boards.csv"
OUT_PATH = ROOT / "data" / "jobs_board_staging.csv"
RUNS_PATH = ROOT / "data" / "board_source_runs.csv"

HEADERS = {
    "User-Agent": "ProfessionalDashboard/0.3 (+https://github.com/ORosa10/ProfessionalDashboard)"
}

STAGING_COLUMNS = [
    "job_id", "canonical_company_id", "company", "title", "description",
    "description_en", "translation_status", "market", "location",
    "priority_locations", "job_url", "source_url", "source_id", "date_posted",
    "discovered_at", "last_seen_at", "relevance_score", "matched_terms",
    "verification", "status", "alternate_job_urls", "duplicate_count",
    "calibration_score", "calibration_note",
]

# These are search queries, not hard inclusion rules. Workstream C subsequently
# orders every retained result and keeps exploration visible.
DEFAULT_QUERIES = [
    "treasury",
    "FP&A",
    "corporate finance",
    "M&A",
    "valuation",
    "investment analyst",
    "portfolio management",
    "financial risk",
    "restructuring",
]

TITLE_FINANCE_MARKERS = (
    "treasury", "fp&a", "finance", "financial", "finanz", "controller",
    "controlling", "corporate finance", "corporate development", "m&a",
    "valuation", "bewertung", "investment", "portfolio", "risk", "risiko",
    "restructuring", "turnaround", "liquidity", "liquidität", "cash management",
    "transaction", "private equity", "asset management",
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _stable_id(source_id: str, external_id: str, url: str) -> str:
    raw = f"{source_id}|{external_id or url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _location_text(value: object) -> str:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, dict):
        return _clean(
            ", ".join(
                str(value.get(key) or "")
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if value.get(key)
            )
        )
    if isinstance(value, list):
        return "; ".join(filter(None, (_location_text(item) for item in value)))
    return ""


def _logical_key(value: object) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\((?:m|w|f|d)(?:\s*/\s*(?:m|w|f|d)){1,4}\)", "", text)
    return re.sub(r"[^a-z0-9à-ž]+", " ", text).strip()


def relevant_finance_title(value: object) -> bool:
    title = _logical_key(value)
    return any(_logical_key(marker) in title for marker in TITLE_FINANCE_MARKERS)


def deduplicate_board_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    """Merge the same company/title advertised through multiple board records."""
    if jobs.empty:
        return jobs
    frame = jobs.copy()
    frame["_company_key"] = frame["company"].map(_logical_key)
    frame["_title_key"] = frame["title"].map(_logical_key)
    rows: list[pd.Series] = []
    for _, group in frame.groupby(["_company_key", "_title_key"], sort=False):
        ranked = group.copy()
        status = (
            ranked["status"]
            if "status" in ranked.columns
            else pd.Series("Open", index=ranked.index)
        )
        ranked["_open_rank"] = status.eq("Open").astype(int)
        row = ranked.sort_values(
            ["_open_rank", "date_posted", "job_id"], ascending=[False, False, True]
        ).iloc[0].copy()
        locations = list(dict.fromkeys(str(v) for v in group["location"] if str(v).strip()))
        urls = list(dict.fromkeys(str(v) for v in group["job_url"] if str(v).strip()))
        terms: set[str] = set()
        for value in group["matched_terms"]:
            terms.update(part.strip() for part in str(value).split(";") if part.strip())
        row["location"] = "; ".join(locations)
        row["priority_locations"] = row["location"]
        row["job_url"] = urls[0] if urls else ""
        row["source_url"] = row["job_url"]
        row["alternate_job_urls"] = "; ".join(urls[1:])
        row["duplicate_count"] = len(group)
        row["matched_terms"] = "; ".join(sorted(terms))
        row["relevance_score"] = len(terms)
        rows.append(row)
    return pd.DataFrame(rows).drop(
        columns=["_company_key", "_title_key", "_open_rank"], errors="ignore"
    )


def _jobposting_from_page(url: str) -> dict | None:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.string or node.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def fetch_jobtech(query: str, limit: int) -> list[dict]:
    response = requests.get(
        "https://jobsearch.api.jobtechdev.se/search",
        params={"q": query, "limit": limit, "offset": 0},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("hits", [])


def discover_platsbanken(queries: list[str], per_query: int) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    jobs: dict[str, dict] = {}
    errors: list[str] = []
    for query in queries:
        try:
            hits = fetch_jobtech(query, per_query)
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}")
            continue
        for item in hits:
            external_id = str(item.get("id") or "")
            url = item.get("webpage_url") or ""
            if not external_id or not url:
                continue
            employer = item.get("employer") or {}
            workplace = item.get("workplace_address") or {}
            location = _clean(
                ", ".join(
                    str(workplace.get(key) or "")
                    for key in ("municipality", "region", "country")
                    if workplace.get(key)
                )
            ) or "Sweden"
            description = (item.get("description") or {}).get("text") or ""
            if not relevant_finance_title(item.get("headline")):
                continue
            job_id = _stable_id("platsbanken-se", external_id, url)
            current = jobs.get(job_id)
            matched = set(str(current.get("matched_terms", "")).split("; ")) if current else set()
            matched.discard("")
            matched.add(query)
            jobs[job_id] = {
                "job_id": job_id,
                "canonical_company_id": "",
                "company": _clean(employer.get("name")) or "Employer not stated",
                "title": _clean(item.get("headline")),
                "description": _clean(description),
                "description_en": "",
                "translation_status": "pending",
                "market": "Sweden",
                "location": location,
                "priority_locations": location,
                "job_url": url,
                "source_url": url,
                "source_id": "platsbanken-se",
                "date_posted": item.get("publication_date") or "",
                "discovered_at": now,
                "last_seen_at": now,
                "relevance_score": len(matched),
                "matched_terms": "; ".join(sorted(matched)),
                "verification": "official JobSearch API vacancy",
                "status": "Open",
                "alternate_job_urls": "",
                "duplicate_count": 0,
                "calibration_score": "",
                "calibration_note": "",
            }
        time.sleep(0.1)
    return list(jobs.values()), errors


def extract_ba_search_links(html: str, limit: int) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    for anchor in soup.select('a[id^="ergebnisliste-item-"][href*="/jobsuche/jobdetail/"]'):
        href = anchor.get("href") or ""
        if href.startswith("/"):
            href = "https://www.arbeitsagentur.de" + href
        heading = anchor.select_one("h2")
        label = _clean(heading.get_text(" ", strip=True) if heading else "")
        links.append((href, re.sub(r"^\d+:\s*", "", label)))
        if len(links) >= limit:
            break
    return links


def _ba_search_links(query: str, limit: int) -> list[tuple[str, str]]:
    url = "https://www.arbeitsagentur.de/jobsuche/suche?" + urlencode(
        {"angebotsart": "1", "was": query, "suchbereich": "jobs"}
    )
    response = requests.get(url, headers=HEADERS, timeout=40)
    response.raise_for_status()
    return extract_ba_search_links(response.text, limit)


def discover_arbeitsagentur(
    queries: list[str], per_query: int, max_details: int
) -> tuple[list[dict], list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    candidates: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    errors: list[str] = []
    for query in queries:
        try:
            for url, label in _ba_search_links(query, per_query):
                candidates.setdefault(url, set()).add(query)
                labels[url] = label
        except Exception as exc:
            errors.append(f"search {query}: {type(exc).__name__}")
        time.sleep(0.15)

    jobs: list[dict] = []
    for url, matched in list(candidates.items())[:max_details]:
        try:
            item = _jobposting_from_page(url)
            if not item:
                raise ValueError("JobPosting JSON-LD missing")
        except Exception as exc:
            errors.append(f"detail {url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        organization = item.get("hiringOrganization") or {}
        locations = item.get("jobLocation") or []
        if isinstance(locations, dict):
            locations = [locations]
        location_bits = []
        for location in locations:
            if isinstance(location, dict):
                location_bits.append(_location_text(location.get("address") or location))
        location = "; ".join(filter(None, location_bits)) or "Germany"
        title = _clean(item.get("title")) or labels.get(url, "")
        if not relevant_finance_title(title):
            continue
        jobs.append({
            "job_id": _stable_id("arbeitsagentur-de", external_id, url),
            "canonical_company_id": "",
            "company": _clean(organization.get("name")) or "Employer not stated",
            "title": title,
            "description": _clean(BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" ")),
            "description_en": "",
            "translation_status": "pending",
            "market": "Germany",
            "location": location,
            "priority_locations": location,
            "job_url": url,
            "source_url": url,
            "source_id": "arbeitsagentur-de",
            "date_posted": item.get("datePosted") or "",
            "discovered_at": now,
            "last_seen_at": now,
            "relevance_score": len(matched),
            "matched_terms": "; ".join(sorted(matched)),
            "verification": "official Bundesagentur JobPosting detail",
            "status": "Open",
            "alternate_job_urls": "",
            "duplicate_count": 0,
            "calibration_score": "",
            "calibration_note": "",
        })
        time.sleep(0.15)
    return jobs, errors


def _merge_with_existing(new: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    if not out_path.exists() or new.empty:
        return new
    old = pd.read_csv(out_path).fillna("").reindex(columns=STAGING_COLUMNS, fill_value="")
    old_idx = old.set_index("job_id")
    new_idx = new.set_index("job_id")
    common = old_idx.index.intersection(new_idx.index)
    if len(common):
        new_idx.loc[common, "discovered_at"] = old_idx.loc[common, "discovered_at"]
    # Keep historical rows visible, but only the current sweep is marked open.
    missing = old_idx.loc[~old_idx.index.isin(new_idx.index)].copy()
    missing["status"] = "Not seen in latest board sweep"
    combined = pd.concat([new_idx, missing]).reset_index()
    return deduplicate_board_jobs(combined)


def translate_with_board_cache(jobs: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    """Reuse earlier board translations before calling the shared translator."""
    if jobs.empty or not out_path.exists():
        return translate_descriptions(jobs)
    old = pd.read_csv(out_path).fillna("")
    if not {"description", "description_en", "translation_status"}.issubset(old.columns):
        return translate_descriptions(jobs)
    cached_en = dict(zip(old["description"], old["description_en"]))
    cached_status = dict(zip(old["description"], old["translation_status"]))
    result = jobs.copy()
    result["description_en"] = result["description"].map(cached_en).fillna("")
    result["translation_status"] = result["description"].map(cached_status).fillna("")
    missing = result["description_en"].eq("")
    if missing.any():
        translated = translate_descriptions(result.loc[missing].copy())
        result.loc[missing, "description_en"] = translated["description_en"]
        result.loc[missing, "translation_status"] = translated["translation_status"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--runs", default=str(RUNS_PATH))
    parser.add_argument("--per-query", type=int, default=8)
    parser.add_argument("--max-details", type=int, default=65)
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--source-id", action="append", default=[])
    args = parser.parse_args()

    boards = pd.read_csv(BOARDS_PATH).fillna("")
    active = boards[
        boards["enabled"].astype(str).str.lower().eq("true")
        & boards["status"].eq("active")
    ]
    if args.source_id:
        active = active[active["board_id"].isin(args.source_id)]

    records: list[dict] = []
    run_rows: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()
    for row in active.itertuples(index=False):
        if row.adapter == "jobtech_api":
            found, errors = discover_platsbanken(DEFAULT_QUERIES, args.per_query)
        elif row.adapter == "arbeitsagentur_html":
            found, errors = discover_arbeitsagentur(
                DEFAULT_QUERIES, args.per_query, args.max_details
            )
        else:
            found, errors = [], [f"Unsupported adapter: {row.adapter}"]
        records.extend(found)
        run_rows.append({
            "run_at": started,
            "board_id": row.board_id,
            "country": row.country,
            "adapter": row.adapter,
            "queries": len(DEFAULT_QUERIES),
            "verified_jobs": len(found),
            "errors": " | ".join(errors[:8]),
        })
        print(f"{row.board_id}: verified={len(found)} errors={len(errors)}")

    out = pd.DataFrame(records).reindex(columns=STAGING_COLUMNS, fill_value="")
    if not out.empty:
        out = deduplicate_board_jobs(out.drop_duplicates("job_id", keep="first"))
        out = calibrate_jobs(out)
        if not args.no_translate:
            out = translate_with_board_cache(out, Path(args.out))
    out_path = Path(args.out)
    out = _merge_with_existing(out, out_path).reindex(columns=STAGING_COLUMNS, fill_value="")
    if not out.empty:
        out = out.sort_values(
            ["status", "calibration_score", "last_seen_at"],
            ascending=[True, False, False],
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    runs_path = Path(args.runs)
    runs = pd.DataFrame(run_rows)
    if runs_path.exists():
        runs = pd.concat([pd.read_csv(runs_path).fillna(""), runs], ignore_index=True).tail(500)
    runs.to_csv(runs_path, index=False)
    print(f"wrote {len(out)} board-sourced roles to {out_path}")


if __name__ == "__main__":
    main()
