from __future__ import annotations

import argparse
import hashlib
import json
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
FOLLOW_HINTS = (
    "job", "jobs", "career", "careers", "vacancy", "vacancies", "position", "role",
    "apply", "search-results", "stellen", "stelle", "karriere",
)
BLOCKED_HINTS = (
    "privacy", "cookie", "terms", "accessibility", "contact", "login", "sign in",
    "talent community", "events", "students", "graduates",
)
SUCCESSFACTORS_HOSTS = ("careers.ey.com", "jobs.deloitte.de")
HEADERS = {
    "User-Agent": "ProfessionalDashboard/0.2 (+https://github.com/ORosa10/ProfessionalDashboard)"
}

MARKET_LOCATION_TERMS = {
    "Czechia": ("czech", "praha", "prague", "brno", "ostrava", ", cz"),
    "Germany": ("germany", "deutschland", "munich", "münchen", "berlin", "frankfurt", "hamburg", ", de"),
    "Austria": ("austria", "österreich", "vienna", "wien", ", at"),
    "Switzerland": ("switzerland", "schweiz", "zurich", "zürich", ", ch"),
    "United Kingdom": ("united kingdom", "uk", "london", "england", ", gb"),
    "Nordics": (
        "sweden", "stockholm", "denmark", "copenhagen", "norway", "oslo",
        "finland", "helsinki", ", se", ", dk", ", no", ", fi",
    ),
}


def allowed(url: str, domains: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return any(
        host == domain.strip().lower() or host.endswith("." + domain.strip().lower())
        for domain in domains.split(";")
        if domain.strip()
    )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def relevance(title: str) -> tuple[int, str]:
    low = title.lower()
    hits = [term for term in ROLE_TERMS if term in low]
    return min(100, 20 + 16 * len(hits)) if hits else 10, "; ".join(hits)


def fetch(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    response.raise_for_status()
    return response


def _iter_jsonld_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld_objects(item)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _iter_jsonld_objects(value["@graph"])


def extract_job_postings(soup: BeautifulSoup, page_url: str = "") -> list[dict]:
    postings: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _iter_jsonld_objects(payload):
            obj_type = obj.get("@type")
            types = obj_type if isinstance(obj_type, list) else [obj_type]
            if any(str(t).lower() == "jobposting" for t in types if t):
                obj["_verification"] = "schema.org/JobPosting JSON-LD"
                postings.append(obj)
    for shell in soup.find_all(
        attrs={"itemtype": re.compile(r"schema\.org/JobPosting", re.IGNORECASE)}
    ):
        title_node = shell.find(attrs={"itemprop": "title"})
        date_node = shell.find(attrs={"itemprop": "datePosted"})
        title = normalize(
            (title_node.get("content") if title_node else "")
            or (title_node.get_text(" ", strip=True) if title_node else "")
        )
        if not title:
            continue
        locations: list[dict] = []
        for address in shell.find_all(attrs={"itemprop": "address"}):
            values: dict[str, str] = {}
            for key in ("addressLocality", "addressRegion", "addressCountry", "postalCode"):
                node = address.find(attrs={"itemprop": key})
                if node:
                    values[key] = normalize(node.get("content") or node.get_text(" ", strip=True))
            if values:
                locations.append({"@type": "Place", "address": values})
        postings.append(
            {
                "@type": "JobPosting",
                "title": title,
                "datePosted": normalize(
                    (date_node.get("content") if date_node else "")
                    or (date_node.get_text(" ", strip=True) if date_node else "")
                ),
                "jobLocation": locations,
                "_verification": "schema.org/JobPosting microdata",
            }
        )
    if not postings and page_url and is_successfactors_job_url(page_url):
        title_meta = soup.find("meta", attrs={"property": "og:title"})
        title = normalize(title_meta.get("content", "") if title_meta else "")
        location_node = soup.select_one(".jobLocation, .jobGeoLocation")
        location = normalize(location_node.get_text(" ", strip=True) if location_node else "")
        job_shell = soup.select_one(".jobDisplayShell, .jobDisplay")
        if title and location and job_shell:
            postings.append(
                {
                    "@type": "JobPosting",
                    "title": title,
                    "jobLocation": {"@type": "Place", "address": location},
                    "_verification": "official ATS vacancy detail",
                }
            )
    return postings


def job_location_text(posting: dict) -> str:
    locations = posting.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    parts: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address") or {}
        if isinstance(address, str):
            parts.append(address)
            continue
        if isinstance(address, dict):
            for key in ("addressLocality", "addressRegion", "addressCountry", "postalCode"):
                value = address.get(key)
                if isinstance(value, dict):
                    value = value.get("name")
                if value:
                    parts.append(str(value))
    remote = posting.get("jobLocationType")
    if remote:
        parts.append(str(remote))
    return normalize(" · ".join(dict.fromkeys(parts)))


def location_matches_market(location: str, market: str) -> bool:
    if not location:
        return True
    low = location.lower()
    terms = MARKET_LOCATION_TERMS.get(market, ())
    return not terms or any(term in low for term in terms)


def should_follow(title: str, href: str) -> bool:
    hay = f"{title} {href}".lower()
    return (
        not any(blocked in hay for blocked in BLOCKED_HINTS)
        and any(hint in hay for hint in FOLLOW_HINTS)
    )


def is_successfactors_job_url(url: str) -> bool:
    """Return True only for an individual SuccessFactors vacancy URL."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    if not any(host == item or host.endswith("." + item) for item in SUCCESSFACTORS_HOSTS):
        return False
    return bool(re.search(r"/(?:ey/)?job/.+/\d+/?$", parsed.path, flags=re.IGNORECASE))


def ordered_follow_links(soup: BeautifulSoup, page_url: str, source: pd.Series) -> list[str]:
    """Prefer real ATS vacancies, ordered by title relevance, over navigation links."""
    links: dict[str, tuple[int, str]] = {}
    for anchor in soup.find_all("a", href=True):
        title = normalize(anchor.get_text(" ", strip=True))
        href = urljoin(page_url, anchor.get("href", ""))
        if not href.startswith("http") or not allowed(href, source.allowed_domains):
            continue
        if is_successfactors_job_url(href):
            score, _ = relevance(title)
            links[href] = (score, title)
        elif should_follow(title, href):
            links.setdefault(href, (0, title))
    return [
        href
        for href, _ in sorted(
            links.items(),
            key=lambda item: (-item[1][0], item[1][1].lower(), item[0]),
        )
    ]


def posting_to_job(posting: dict, page_url: str, source: pd.Series, started: str) -> dict | None:
    title = normalize(str(posting.get("title") or posting.get("name") or ""))
    if not title:
        return None
    location = job_location_text(posting)
    if not location_matches_market(location, source.market):
        return None
    canonical_url = posting.get("url") or page_url
    if not isinstance(canonical_url, str) or not canonical_url.startswith("http"):
        canonical_url = page_url
    score, terms = relevance(title)
    identifier = posting.get("identifier") or {}
    if isinstance(identifier, dict):
        external_id = identifier.get("value") or identifier.get("name") or ""
    else:
        external_id = str(identifier)
    stable_key = external_id or canonical_url
    job_id = hashlib.sha1(
        f"{source.canonical_company_id}|{stable_key}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "job_id": job_id,
        "canonical_company_id": source.canonical_company_id,
        "company": source.company,
        "title": title,
        "market": source.market,
        "location": location,
        "priority_locations": source.priority_locations,
        "job_url": canonical_url,
        "source_url": source.seed_url,
        "source_id": source.source_id,
        "date_posted": normalize(str(posting.get("datePosted") or "")),
        "discovered_at": started,
        "last_seen_at": started,
        "relevance_score": score,
        "matched_terms": terms,
        "verification": posting.get("_verification") or "schema.org/JobPosting",
        "status": "Open",
    }


def discover_jobs(source: pd.Series, max_pages: int = 40) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    queue = [(source.seed_url, 0)]
    queued = {source.seed_url}
    visited: set[str] = set()
    jobs: dict[str, dict] = {}
    errors: list[str] = []
    candidate_pages = 0

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
        postings = extract_job_postings(soup, response.url)
        if postings:
            candidate_pages += 1
            for posting in postings:
                job = posting_to_job(posting, response.url, source, started)
                if job:
                    jobs[job["job_id"]] = job

        if depth < 2 and not postings:
            for href in ordered_follow_links(soup, response.url, source):
                if href not in queued:
                    queue.append((href, depth + 1))
                    queued.add(href)
        time.sleep(0.35)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": len(visited),
        "candidate_job_pages": candidate_pages,
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def merge_jobs(new_jobs: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "job_id", "canonical_company_id", "company", "title", "market", "location",
        "priority_locations", "job_url", "source_url", "source_id", "date_posted",
        "discovered_at", "last_seen_at", "relevance_score", "matched_terms",
        "verification", "status",
    ]
    old = pd.read_csv(JOBS_PATH).fillna("") if JOBS_PATH.exists() else pd.DataFrame()
    if "verification" not in old.columns:
        old = pd.DataFrame(columns=columns)
    else:
        old = old.reindex(columns=columns, fill_value="")
    if new_jobs.empty:
        return old

    new_jobs = new_jobs[columns].copy()
    if old.empty:
        return new_jobs.sort_values(["relevance_score", "company"], ascending=[False, True])

    old_idx = old.set_index("job_id")
    new_idx = new_jobs.set_index("job_id")
    common = old_idx.index.intersection(new_idx.index)
    if len(common):
        new_idx.loc[common, "discovered_at"] = old_idx.loc[common, "discovered_at"]
        previously_closed = old_idx.loc[common, "status"].eq("Closed")
        if previously_closed.any():
            closed_ids = previously_closed[previously_closed].index
            new_idx.loc[closed_ids, "status"] = "Closed"
    missing = old_idx.loc[~old_idx.index.isin(new_idx.index)]
    combined = pd.concat([new_idx, missing])
    return combined.reset_index()[columns].sort_values(
        ["relevance_score", "last_seen_at"], ascending=[False, False]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args()
    sources = pd.read_csv(SOURCES_PATH).fillna("")
    sources = sources[sources["enabled"].astype(str).str.lower().eq("true")]
    all_jobs: list[dict] = []
    runs: list[dict] = []
    for _, source in sources.iterrows():
        host = urlparse(source.seed_url).netloc.lower().split(":")[0]
        has_dedicated_adapter = any(
            host == item or host.endswith("." + item) for item in SUCCESSFACTORS_HOSTS
        )
        page_limit = args.max_pages if has_dedicated_adapter else min(args.max_pages, 8)
        jobs, run = discover_jobs(source, max_pages=page_limit)
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
    print(
        f"Checked {len(sources)} sources; stored {len(merged)} verified jobs; "
        f"verified {len(all_jobs)} postings this run."
    )


if __name__ == "__main__":
    main()
