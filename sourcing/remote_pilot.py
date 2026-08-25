"""Remote-work sourcing (workstream D).

Pulls remote roles from public remote-board feeds (Remote OK, Remotive,
We Work Remotely), keeps a broad finance/treasury/risk/investment candidate
set, and writes it in the same staging schema as the other sourcing lanes.
Semantic fit is deliberately left to C. Remote employability is deliberately
left to the separate pre-J actionability gate.

The runner is deterministic and zero-metered-cost. Temporary source outages do
not erase the last successful snapshot for that source.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]

try:  # reuse transparent calibration ordering when its dependencies are present
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

# D uses title-level discovery only. The baseline must never disappear just
# because a learned positive-rule file happens to contain a narrower vocabulary.
# Learned C-positive concepts are therefore additive search intelligence.
_DEFAULT_FINANCE_TERMS = [
    "treasury", "risk", "valuation", "quant", "investment", "portfolio",
    "corporate finance", "corporate development", "financial analyst", "finance",
    "fp&a", "fp & a", "derivative", "capital markets", "fixed income", "trader",
    "trading", "controller", "controlling", "actuar", "m&a", "private equity",
    "hedge fund", "asset management", "credit analyst", "finance manager",
    "structurer", "liquidity", "cfo",
]


def _load_targeting_terms() -> list[str]:
    """Return stable D discovery terms plus learned C-positive concepts.

    C may teach sourcing additional useful concepts, but a learned rules file
    must not replace the baseline and accidentally starve remote discovery.
    """
    terms = list(_DEFAULT_FINANCE_TERMS)
    try:
        with open(ROOT / "data" / "calibration_rules.json", encoding="utf-8") as fh:
            data = json.load(fh)
        for rule in data.get("positive_rules", {}).values():
            terms.extend(str(t).strip().lower() for t in rule.get("terms", []))
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError, TypeError):
        pass
    return [term for term in dict.fromkeys(terms) if term]


FINANCE_TITLE_TERMS = _load_targeting_terms()

# Strong project/interim evidence only. Generic words such as "contract" inside
# a benefits, customer or legal paragraph must not silently delete a permanent
# remote role from D.
PROJECT_TITLE_PATTERNS = [
    r"\bcontract(?:or)?\b", r"\binterim\b", r"\bfreelance\b",
    r"\bfixed[- ]term\b", r"\btemporary\b", r"\bfractional\b",
    r"\bsecondment\b", r"\bmaternity cover\b", r"\bftc\b",
    r"\b(?:3|6|9|12)[- ]month\b",
]
PROJECT_DESCRIPTION_PATTERNS = [
    r"\b(?:contract|interim|freelance|fixed[- ]term|temporary)\s+(?:role|position|assignment|engagement)\b",
    r"\b(?:3|6|9|12)[- ]month\s+(?:contract|assignment|fixed[- ]term)\b",
    r"\bcontract\s+(?:length|duration)\s*[:\-]",
    r"\bemployment\s+type\s*[:\-]\s*(?:contract|temporary|fixed[- ]term|freelance)\b",
    r"\bmaternity cover\b",
    r"\bsecondment\b",
    r"\bfractional\s+(?:role|position|cfo|finance)\b",
]

REMOTE_SCOPE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:headquarters|location|work location)\s*:\s*remote\s*[-–—,:()]?\s*(?:the\s+)?(?:u\.?s\.?|united states)\b", "Remote - US"),
    (r"\bremote\s*[-–—,:()]\s*(?:the\s+)?(?:u\.?s\.?|united states)\b", "Remote - US"),
    (r"\bremote\s+(?:within|in|from)\s+(?:the\s+)?(?:u\.?s\.?|united states)\b", "Remote - US"),
    (r"\b(?:candidates?|applicants?)\s+(?:must|need to)\s+(?:be\s+)?(?:based|located|resident|reside)\s+(?:in|within)\s+(?:the\s+)?(?:u\.?s\.?|united states)\b", "Remote - US"),
    (r"\b(?:headquarters|location|work location)\s*:\s*remote\s*[-–—,:()]?\s*canada\b", "Remote - Canada"),
    (r"\bremote\s+(?:within|in|from)\s+canada\b", "Remote - Canada"),
    (r"\bremote\s+(?:within|in|from)\s+(?:the\s+)?(?:eu|europe|european union)\b", "Remote - Europe"),
    (r"\b(?:location|work location)\s*:\s*remote\s*[-–—,:()]?\s*(?:eu|europe|emea)\b", "Remote - EMEA"),
    (r"\bremote\s*[-–—,:()]\s*emea\b", "Remote - EMEA"),
    (r"\b(?:worldwide|global)\s+remote\b", "Remote - Worldwide"),
    (r"\bremote\s+(?:worldwide|globally)\b", "Remote - Worldwide"),
    (r"\banywhere\s+in\s+the\s+world\b", "Remote - Worldwide"),
]

UA = {"User-Agent": "Mozilla/5.0 ProfessionalDashboard/1.0"}


def _clean(text: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", str(text or "")))).strip()


def is_project_role(title: str, desc: str) -> bool:
    """Classify only explicit contract/interim evidence for optional E routing."""
    title_text = _clean(title).lower()
    if any(re.search(pattern, title_text, flags=re.IGNORECASE) for pattern in PROJECT_TITLE_PATTERNS):
        return True
    desc_text = _clean(desc).lower()
    return any(re.search(pattern, desc_text, flags=re.IGNORECASE) for pattern in PROJECT_DESCRIPTION_PATTERNS)


def remote_scope_hint(title: str, desc: str, meta: str = "") -> str:
    """Preserve explicit remote scope as source evidence; never infer eligibility."""
    evidence = f"{_clean(title)} {_clean(meta)} {_clean(desc)}".lower()
    for pattern, label in REMOTE_SCOPE_PATTERNS:
        if re.search(pattern, evidence, flags=re.IGNORECASE):
            return label
    return "Remote"


def _relevant(title: str, meta: str = "", src: str = "") -> list[str]:
    """Broad finance discovery from the role title only.

    Remote-board categories are not semantic truth: Remotive's finance/legal
    category also contains legal roles and WWR combines management with finance.
    C remains the role-content assessor, but D should at least require a finance
    title signal before spending C review capacity.
    """
    del meta, src  # retained in signature for source adapters / future diagnostics
    title_text = f" {title} ".lower()
    return [term for term in FINANCE_TITLE_TERMS if term in title_text]


def fetch_remoteok() -> tuple[list[tuple], bool]:
    out: list[tuple] = []
    try:
        response = requests.get("https://remoteok.com/api", headers=UA, timeout=30)
        response.raise_for_status()
        for item in response.json():
            if not isinstance(item, dict) or not item.get("position"):
                continue
            out.append((
                _clean(item.get("position")), _clean(item.get("company")),
                _clean(item.get("description")), item.get("url", ""),
                "remoteok", str(item.get("date", "")), _clean(item.get("location", "")),
            ))
        return out, True
    except Exception as exc:
        print("remoteok failed:", exc)
        return out, False


def fetch_remotive() -> tuple[list[tuple], bool]:
    out: list[tuple] = []
    try:
        response = requests.get(
            "https://remotive.com/api/remote-jobs?category=finance-legal",
            headers=UA,
            timeout=30,
        )
        response.raise_for_status()
        for item in response.json().get("jobs", []):
            meta = " | ".join(
                value for value in [
                    _clean(item.get("category", "")),
                    _clean(item.get("candidate_required_location", "")),
                ] if value
            )
            out.append((
                _clean(item.get("title")), _clean(item.get("company_name")),
                _clean(item.get("description")), item.get("url", ""),
                "remotive", str(item.get("publication_date", "")), meta,
            ))
        return out, True
    except Exception as exc:
        print("remotive failed:", exc)
        return out, False


def fetch_wwr() -> tuple[list[tuple], bool]:
    out: list[tuple] = []
    feed = "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss"
    try:
        response = requests.get(feed, headers=UA, timeout=30)
        response.raise_for_status()
        for item in ET.fromstring(response.content).iter("item"):
            title = _clean(item.findtext("title"))
            company, role = "", title
            if ":" in title:
                company, role = [part.strip() for part in title.split(":", 1)]
            out.append((
                role, company, _clean(item.findtext("description")),
                _clean(item.findtext("link")), "weworkremotely",
                _clean(item.findtext("pubDate")), "management-and-finance",
            ))
        return out, True
    except Exception as exc:
        print("wwr failed:", feed, exc)
        return out, False


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=STAGING_COLUMNS)


def _read_previous(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_frame()
    try:
        return pd.read_csv(path).fillna("").reindex(columns=STAGING_COLUMNS, fill_value="")
    except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
        return _empty_frame()


def merge_remote_snapshot(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    successful_sources: set[str],
) -> pd.DataFrame:
    """Replace successful-source snapshots and preserve temporarily failed ones."""
    current = current.reindex(columns=STAGING_COLUMNS, fill_value="").fillna("")
    previous = previous.reindex(columns=STAGING_COLUMNS, fill_value="").fillna("")
    if previous.empty:
        return current.drop_duplicates("job_id", keep="first").reset_index(drop=True)
    preserve = previous[~previous["source_id"].astype(str).isin(successful_sources)].copy()
    merged = pd.concat([current, preserve], ignore_index=True, sort=False).fillna("")
    if merged.empty:
        return _empty_frame()
    return merged.drop_duplicates("job_id", keep="first").reindex(columns=STAGING_COLUMNS, fill_value="").reset_index(drop=True)


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


def _record(
    title: str,
    company: str,
    desc: str,
    url: str,
    src: str,
    posted: str,
    meta: str,
    hits: list[str],
    now: str,
) -> dict:
    location = remote_scope_hint(title, desc, meta)
    return {
        "job_id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
        "canonical_company_id": "",
        "company": company or src.title(),
        "title": title,
        "description": desc,
        "description_en": desc,
        "translation_status": "assumed_en",
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
        "verification": "board_listing",
        "status": "Open",
        "alternate_job_urls": "",
        "duplicate_count": 0,
        "calibration_score": "",
        "calibration_note": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "data" / "jobs_remote_staging.csv"))
    parser.add_argument(
        "--projects-out",
        help="Optional separate shadow/staging output for remote contract/interim roles so E can ingest them without polluting D.",
    )
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
        raise RuntimeError("All remote sources failed and no previous snapshot exists")

    permanent_records: list[dict] = []
    project_records: list[dict] = []
    for title, company, desc, url, src, posted, meta in remoteok + remotive + wwr:
        if not title or not url:
            continue
        hits = _relevant(title, meta, src)
        if not hits:
            continue
        record = _record(title, company, desc, url, src, posted, meta, hits, now)
        if is_project_role(title, desc):
            project_records.append(record)
        else:
            permanent_records.append(record)

    current = _records_frame(permanent_records)
    merged = merge_remote_snapshot(current, previous, successful_sources)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    print(
        f"wrote {len(merged)} remote permanent roles to {out_path} "
        f"({len(project_records)} explicit project/interim roles separated)"
    )

    if args.projects_out:
        projects_path = Path(args.projects_out)
        previous_projects = _read_previous(projects_path)
        projects = merge_remote_snapshot(
            _records_frame(project_records),
            previous_projects,
            successful_sources,
        )
        projects_path.parent.mkdir(parents=True, exist_ok=True)
        projects.to_csv(projects_path, index=False)
        print(f"wrote {len(projects)} remote project/interim roles to {projects_path}")


if __name__ == "__main__":
    main()
