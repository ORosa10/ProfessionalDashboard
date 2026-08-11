from __future__ import annotations

import argparse
import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "job_sources_pilot.csv"
JOBS_PATH = ROOT / "data" / "jobs.csv"
RUNS_PATH = ROOT / "data" / "source_runs.csv"

ROLE_TERMS = (
    "treasury", "market risk", "financial risk", "risk management", "valuation",
    "derivative", "hedge", "commodity", "energy", "corporate finance", "deals",
    "transaction", "strategy", "restructuring", "financial modelling", "financial modeling",
    "finance transformation", "asset management", "investment", "portfolio", "quant",
    "analytics", "capital markets", "m&a", "merger", "acquisition",
)
JOB_HINTS = ("job", "jobs", "career", "careers", "vacancy", "vacancies", "position", "role", "apply")
BLOCKED_HINTS = ("privacy", "cookie", "terms", "accessibility", "contact", "login", "sign in", "talent community")
HEADERS = {"User-Agent": "ProfessionalDashboard/0.1 (+https://github.com/ORosa10/ProfessionalDashboard)"}


def allowed(url: str, domains: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return any(host == d.strip().lower() or host.endswith("." + d.strip().lower()) for d in domains.split(";") if d.strip())


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def looks_like_job(title: str, url: str) -> bool:
    hay = f"{title} {url}".lower()
    return len(title) >= 4 and any(h in hay for h in JOB_HINTS) and not any(b in hay for b in BLOCKED_HINTS)


def relevance(title: str) -> tuple[int, str]:
    low = title.lower()
    hits = [term for term in ROLE_TERMS if term in low]
    return min(100, 20 + 16 * len(hits)) if hits else 10, "; ".join(hits)


def fetch(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    response.raise_for_status()
    return response


def discover_jobs(source: pd.Series, max_pages: int = 8) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    queue = [(source.seed_url, 0)]
    visited: set[str] = set()
    jobs: dict[str, dict] = {}
    errors: list[str] = []

    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)
        if url in visited or not allowed(url, source.allowed_domains):
            continue
        visited.add(url)
        try:
            response = fetch(url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            title = normalize(anchor.get_text(" ", strip=True))
            href = urljoin(response.url, anchor.get("href", ""))
            if not href.startswith("http") or not allowed(href, source.allowed_domains):
                continue
            if looks_like_job(title, href):
                score, terms = relevance(title)
                job_id = hashlib.sha1(f"{source.canonical_company_id}|{href}".encode()).hexdigest()[:16]
                jobs[job_id] = {
                    "job_id": job_id,
                    "canonical_company_id": source.canonical_company_id,
                    "company": source.company,
                    "title": title,
                    "market": source.market,
                    "priority_locations": source.priority_locations,
                    "job_url": href,
                    "source_url": source.seed_url,
                    "source_id": source.source_id,
                    "discovered_at": started,
                    "last_seen_at": started,
                    "relevance_score": score,
                    "matched_terms": terms,
                    "status": "New",
                }
            elif depth < 1:
                hay = f"{title} {href}".lower()
                if any(h in hay for h in JOB_HINTS):
                    queue.append((href, depth + 1))
        time.sleep(0.4)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": len(visited),
        "jobs_found": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def merge_jobs(new_jobs: pd.DataFrame) -> pd.DataFrame:
    columns = ["job_id", "canonical_company_id", "company", "title", "market", "priority_locations", "job_url", "source_url", "source_id", "discovered_at", "last_seen_at", "relevance_score", "matched_terms", "status"]
    if JOBS_PATH.exists():
        old = pd.read_csv(JOBS_PATH).fillna("")
    else:
        old = pd.DataFrame(columns=columns)
    if new_jobs.empty:
        return old
    if old.empty:
        return new_jobs[columns].sort_values(["relevance_score", "company"], ascending=[False, True])
    old_idx = old.set_index("job_id")
    new_idx = new_jobs.set_index("job_id")
    common = old_idx.index.intersection(new_idx.index)
    old_idx.loc[common, "last_seen_at"] = new_idx.loc[common, "last_seen_at"]
    additions = new_idx.loc[new_idx.index.difference(old_idx.index)]
    merged = pd.concat([old_idx, additions]).reset_index()
    return merged[columns].sort_values(["relevance_score", "last_seen_at"], ascending=[False, False])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=8)
    args = parser.parse_args()
    sources = pd.read_csv(SOURCES_PATH).fillna("")
    sources = sources[sources["enabled"].astype(str).str.lower().eq("true")]
    all_jobs: list[dict] = []
    runs: list[dict] = []
    for _, source in sources.iterrows():
        jobs, run = discover_jobs(source, max_pages=args.max_pages)
        all_jobs.extend(jobs)
        runs.append(run)
    merged = merge_jobs(pd.DataFrame(all_jobs))
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(JOBS_PATH, index=False)
    run_df = pd.DataFrame(runs)
    if RUNS_PATH.exists():
        history = pd.read_csv(RUNS_PATH).fillna("")
        run_df = pd.concat([history, run_df], ignore_index=True).tail(2000)
    run_df.to_csv(RUNS_PATH, index=False)
    print(f"Checked {len(sources)} sources; stored {len(merged)} jobs; found {len(all_jobs)} links this run.")


if __name__ == "__main__":
    main()
