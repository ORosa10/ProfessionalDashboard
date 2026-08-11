from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from langdetect import LangDetectException, detect

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "job_sources_pilot.csv"
JOBS_PATH = ROOT / "data" / "jobs.csv"
RUNS_PATH = ROOT / "data" / "source_runs.csv"
FEEDBACK_PATH = ROOT / "data" / "job_feedback.csv"

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

NON_JOB_TITLE_PATTERNS = (
    r"^interest in .+\??$",
    r"^register your interest",
    r"^join (our|the) talent (community|network)",
    r"^talent (community|network)",
    r"^general application",
    r"^spontaneous application",
)

ROLE_SECTION_STARTS = (
    "your key responsibilities", "key responsibilities", "your responsibilities",
    "what you will do", "what you'll do", "your impact", "your tasks", "role overview",
    "responsibilities", "your contribution", "deine aufgaben", "das erwartet dich",
    "ihre aufgaben", "dein beitrag", "the opportunity", "your role", "the role",
    "dine arbejdsopgaver", "dina arbetsuppgifter", "tehtäväsi",
)
ROLE_SECTION_ENDS = (
    "what we offer", "what you can expect", "what we look for", "who you are",
    "skills and attributes", "to qualify for the role", "about ey", "about deloitte",
    "about pwc", "about kpmg", "our benefits", "benefits", "apply now",
    "skills for your success", "your profile", "qualifications", "ready to apply",
    "kontakt", "contact us", "wir bieten", "das bieten wir",
)

GENERIC_OPENING_PATTERNS = (
    r"^at ey[, ]+we(?:'re| are).{0,900}?(?=(?:your impact|the opportunity|your role|what you(?:'ll| will) do|responsibilities)\b)",
    r"^are you ready to shape your future with confidence\??\s*",
    r"^at deloitte[, ].{0,900}?(?=(?:your impact|the opportunity|your role|what you(?:'ll| will) do|responsibilities)\b)",
    r"^at pwc[, ].{0,900}?(?=(?:your impact|the opportunity|your role|what you(?:'ll| will) do|responsibilities)\b)",
    r"^at kpmg[, ].{0,900}?(?=(?:your impact|the opportunity|your role|what you(?:'ll| will) do|responsibilities)\b)",
)
SUCCESSFACTORS_HOSTS = ("careers.ey.com", "jobs.deloitte.de", "jobs.kpmg.de")
PHENOM_HOSTS = ("jobs.pwc.de", "jobs.pwc.co.uk")
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


def description_text(value) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        value = value.get("value") or value.get("text") or ""
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return normalize(text)[:4500]


def is_real_job_title(title: str) -> bool:
    candidate = normalize(title).lower()
    return bool(candidate) and not any(
        re.search(pattern, candidate, flags=re.IGNORECASE)
        for pattern in NON_JOB_TITLE_PATTERNS
    )


def focus_role_description(value: str) -> str:
    """Keep the vacancy substance and remove employer-brand/application boilerplate."""
    text = normalize(value)
    if not text:
        return ""
    for pattern in GENERIC_OPENING_PATTERNS:
        text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip(" :-–—")

    low = text.lower()
    preferred_markers = ROLE_SECTION_STARTS[:-3]
    preferred = [
        low.find(marker) for marker in preferred_markers if 0 <= low.find(marker) <= 1300
    ]
    fallback = [low.find(marker) for marker in ROLE_SECTION_STARTS[-3:] if low.find(marker) >= 0]
    starts = preferred or fallback
    if starts:
        first = min(starts)
        if first <= 1300:
            text = text[first:]

    low = text.lower()
    end_positions = [
        low.find(marker, 60)
        for marker in ROLE_SECTION_ENDS
        if low.find(marker, 60) >= 0
    ]
    if end_positions:
        text = text[:min(end_positions)]
    return normalize(text).strip(" :-–—")[:1800]


def translate_descriptions(jobs: pd.DataFrame) -> pd.DataFrame:
    if jobs.empty:
        return jobs
    existing: dict[str, str] = {}
    if JOBS_PATH.exists():
        old = pd.read_csv(JOBS_PATH).fillna("")
        if {"description", "description_en"}.issubset(old.columns):
            existing = dict(zip(old["description"], old["description_en"]))

    translator = GoogleTranslator(source="auto", target="en")
    cache = dict(existing)
    translated: list[str] = []
    statuses: list[str] = []
    for raw in jobs.get("description", pd.Series("", index=jobs.index)).fillna(""):
        text = description_text(raw)
        if not text:
            translated.append("")
            statuses.append("missing")
            continue
        if cache.get(text):
            translated.append(focus_role_description(cache[text]))
            statuses.append("cached")
            continue
        try:
            language = detect(text)
        except LangDetectException:
            language = "unknown"
        if language == "en":
            english = text
            status = "original-en"
        else:
            try:
                english = normalize(translator.translate(text))
                status = f"translated-{language}"
            except Exception:
                english = text
                status = f"translation-failed-{language}"
        english = focus_role_description(english)
        cache[text] = english
        translated.append(english)
        statuses.append(status)
        time.sleep(0.15)
    result = jobs.copy()
    result["description_en"] = translated
    result["translation_status"] = statuses
    return result


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
        description_node = shell.find(attrs={"itemprop": "description"})
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
                "description": description_text(
                    description_node.get_text(" ", strip=True) if description_node else ""
                ),
                "_verification": "schema.org/JobPosting microdata",
            }
        )
    if not postings and page_url and is_successfactors_job_url(page_url):
        title_meta = soup.find("meta", attrs={"property": "og:title"})
        title = normalize(title_meta.get("content", "") if title_meta else "")
        location_node = soup.select_one(".jobLocation, .jobGeoLocation")
        location = normalize(location_node.get_text(" ", strip=True) if location_node else "")
        job_shell = soup.select_one(".jobDisplayShell, .jobDisplay")
        description_node = soup.select_one(".jobdescription")
        if title and location and job_shell:
            postings.append(
                {
                    "@type": "JobPosting",
                    "title": title,
                    "jobLocation": {"@type": "Place", "address": location},
                    "description": description_text(
                        description_node.get_text(" ", strip=True) if description_node else ""
                    ),
                    "_verification": "official ATS vacancy detail",
                }
            )
    return postings


def extract_phenom_records(html: str) -> tuple[list[dict], int]:
    """Read public, server-rendered job results from a Phenom career page."""
    marker = "phApp.ddo = "
    start = html.find(marker)
    if start < 0:
        return [], 0
    try:
        payload, _ = json.JSONDecoder().raw_decode(html[start + len(marker):])
        search = payload.get("eagerLoadRefineSearch", {})
        data = search.get("data", search)
        return data.get("jobs", []) or [], int(
            data.get("totalHits") or search.get("totalHits") or search.get("hits") or 0
        )
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return [], 0


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
            values: list[str] = []
            for key in ("addressLocality", "addressRegion", "addressCountry"):
                value = address.get(key)
                if isinstance(value, dict):
                    value = value.get("name")
                if value and str(value) not in values:
                    values.append(str(value))
            if values:
                parts.append(", ".join(values))
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
    return bool(
        re.search(
            r"/(?:ey/)?job/.+/\d+(?:-[a-z]{2}_[a-z]{2})?/?$",
            parsed.path,
            flags=re.IGNORECASE,
        )
    )


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
    if not is_real_job_title(title):
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
        "description": description_text(posting.get("description")),
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


def normalized_role_title(title: str) -> str:
    value = normalize(title).lower()
    value = re.sub(r"\((?:m|w|f|d)(?:\s*/\s*(?:m|w|f|d)){1,4}\)", "", value)
    value = re.sub(r"\b(?:m|w|f|d)(?:\s*/\s*(?:m|w|f|d)){2,4}\b", "", value)
    value = re.sub(r"[^a-z0-9à-ž]+", " ", value)
    return normalize(value)


def _split_unique(values, separator: str = " · ") -> str:
    pieces: list[str] = []
    for value in values:
        for piece in re.split(r"\s*(?:·|;|\|)\s*", str(value or "")):
            piece = normalize(piece)
            if piece and piece not in pieces:
                pieces.append(piece)
    return separator.join(pieces)


def deduplicate_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    """Merge identical roles advertised through multiple city/requisition pages."""
    if jobs.empty:
        return jobs
    jobs = jobs[jobs["title"].map(is_real_job_title)].copy()
    jobs["_role_key"] = jobs["title"].map(normalized_role_title)
    feedback: dict[str, tuple[str, str]] = {}
    if FEEDBACK_PATH.exists():
        saved = pd.read_csv(FEEDBACK_PATH).fillna("")
        feedback = {
            str(row.opportunity_id): (str(row.feedback), str(row.comment))
            for row in saved.itertuples()
        }

    merged_rows: list[pd.Series] = []
    for _, group in jobs.groupby(["canonical_company_id", "_role_key"], sort=False):
        ranked = group.copy()
        ranked["_feedback_value"] = ranked["job_id"].map(
            lambda job_id: int(
                bool(feedback.get(str(job_id), ("", ""))[1])
                or feedback.get(str(job_id), ("Unrated", ""))[0] != "Unrated"
            )
        )
        ranked = ranked.sort_values(
            ["_feedback_value", "date_posted", "job_id"],
            ascending=[False, False, True],
        )
        row = ranked.iloc[0].copy()
        row["location"] = _split_unique(group["location"])
        row["market"] = _split_unique(group["market"], separator="; ")
        row["priority_locations"] = _split_unique(
            group["priority_locations"], separator="; "
        )
        urls = list(dict.fromkeys(str(url) for url in group["job_url"] if url))
        row["job_url"] = urls[0] if urls else ""
        row["alternate_job_urls"] = "; ".join(urls[1:])
        row["duplicate_count"] = len(group)
        merged_rows.append(row)
    return pd.DataFrame(merged_rows).drop(
        columns=["_role_key", "_feedback_value"], errors="ignore"
    )


def calibrate_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    """Apply transparent, feedback-derived review ordering without hard exclusions."""
    if jobs.empty:
        return jobs
    result = jobs.copy()
    scores: list[int] = []
    notes: list[str] = []
    for row in result.itertuples():
        text = f"{getattr(row, 'title', '')} {getattr(row, 'description_en', '')}".lower()
        score = 50
        positive: list[str] = []
        caution: list[str] = []
        positive_rules = {
            "transactions / M&A": ("transaction", "m&a", "merger", "acquisition"),
            "corporate finance / valuation": ("corporate finance", "valuation", "financial model"),
            "treasury / FP&A": ("treasury", "fp&a", "financial planning", "controlling"),
            "finance transformation / analytics": ("finance transformation", "finance analytics", "data analy"),
        }
        caution_rules = {
            "junior or graduate level": ("intern", "graduate", "entry level", "berufseinstieg", "assistant"),
            "likely above target seniority": ("director", "partner", "senior manager", "head of "),
            "tax-heavy": (" tax ", "taxation"),
            "SAP-heavy": (" sap ",),
            "accounting / audit-heavy": ("accounting", "audit", "assurance", "wirtschaftsprüfung"),
            "internal HR/services": ("human resources", "recruit", "internal services"),
            "forensics / compliance-heavy": ("forensic", "compliance"),
        }
        padded = f" {text} "
        for label, terms in positive_rules.items():
            if any(term in padded for term in terms):
                positive.append(label)
                score += 10
        for label, terms in caution_rules.items():
            if any(term in padded for term in terms):
                caution.append(label)
                score -= 14 if label == "junior or graduate level" else 9
        if re.search(r"\b(?:senior consultant|consultant|analyst|associate|specialist)\b", text):
            positive.append("plausible level; verify responsibilities")
            score += 5
        scores.append(max(0, min(100, score)))
        parts: list[str] = []
        if positive:
            parts.append("Positive: " + ", ".join(dict.fromkeys(positive)))
        if caution:
            parts.append("Check: " + ", ".join(dict.fromkeys(caution)))
        notes.append(". ".join(parts) or "Exploration: no strong signal yet")
    result["calibration_score"] = scores
    result["calibration_note"] = notes
    return result


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


def discover_phenom_jobs(source: pd.Series, max_pages: int = 10) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    parsed_seed = urlparse(source.seed_url)
    query = dict(parse_qsl(parsed_seed.query))
    query.setdefault("keywords", "finance")
    detail_prefix = parsed_seed.path.rsplit("/search-results", 1)[0]
    records: dict[str, dict] = {}
    errors: list[str] = []
    pages_checked = 0
    total = 0

    for page in range(max_pages):
        query.update({"from": str(page * 10), "s": "1"})
        listing_url = urlunparse(parsed_seed._replace(query=urlencode(query)))
        try:
            response = fetch(listing_url)
        except Exception as exc:
            errors.append(f"{listing_url}: {type(exc).__name__}")
            break
        pages_checked += 1
        page_records, total = extract_phenom_records(response.text)
        if not page_records:
            break
        for record in page_records:
            job_id = normalize(str(record.get("jobId") or record.get("reqId") or ""))
            title = normalize(str(record.get("title") or ""))
            if job_id and is_real_job_title(title):
                records[job_id] = record
        if len(records) >= total:
            break
        time.sleep(0.2)

    jobs: dict[str, dict] = {}
    candidate_pages = 0
    for record_id, record in records.items():
        detail_url = urlunparse(
            parsed_seed._replace(
                path=f"{detail_prefix}/job/{record_id}", query="", fragment=""
            )
        )
        try:
            response = fetch(detail_url)
            postings = extract_job_postings(BeautifulSoup(response.text, "html.parser"), response.url)
        except Exception as exc:
            errors.append(f"{detail_url}: {type(exc).__name__}")
            continue
        if not postings:
            continue
        candidate_pages += 1
        for posting in postings:
            posting.setdefault("identifier", {"value": record_id})
            posting.setdefault("url", response.url)
            if not posting.get("jobLocation"):
                locations = record.get("multi_location") or [record.get("location")]
                posting["jobLocation"] = [
                    {"@type": "Place", "address": location}
                    for location in locations if location
                ]
            job = posting_to_job(posting, response.url, source, started)
            if job:
                jobs[job["job_id"]] = job
        time.sleep(0.25)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": pages_checked + len(records),
        "candidate_job_pages": candidate_pages,
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def discover_successfactors_sitemap_jobs(
    source: pd.Series, max_jobs: int = 80
) -> tuple[list[dict], dict]:
    """Use an official SuccessFactors sitemap when its search results are JS-only."""
    started = datetime.now(timezone.utc).isoformat()
    parsed = urlparse(source.seed_url)
    sitemap_url = urlunparse(parsed._replace(path="/sitemap.xml", query="", fragment=""))
    errors: list[str] = []
    jobs: dict[str, dict] = {}
    try:
        response = fetch(sitemap_url)
        urls = [html.unescape(value) for value in re.findall(r"<loc>(.*?)</loc>", response.text)]
    except Exception as exc:
        urls = []
        errors.append(f"{sitemap_url}: {type(exc).__name__}")

    signals = ROLE_TERMS + (
        "finance", "financial", "controlling", "bank", "deal", "accounting",
        "performance management", "business analyst", "cfo", "due diligence",
    )
    candidates: list[tuple[int, str]] = []
    for url in urls:
        decoded = unquote(url).replace("-", " ").lower()
        if "/job/" not in url or not any(signal in decoded for signal in signals):
            continue
        score, _ = relevance(decoded)
        candidates.append((score, url))
    candidates.sort(key=lambda item: (-item[0], item[1]))

    candidate_pages = 0
    for _, url in candidates[:max_jobs]:
        try:
            response = fetch(url)
            postings = extract_job_postings(BeautifulSoup(response.text, "html.parser"), response.url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            continue
        if postings:
            candidate_pages += 1
        for posting in postings:
            posting.setdefault("url", response.url)
            job = posting_to_job(posting, response.url, source, started)
            if job:
                jobs[job["job_id"]] = job
        time.sleep(0.25)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": 1 + min(len(candidates), max_jobs),
        "candidate_job_pages": candidate_pages,
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def _kpmg_public_api_config(seed_url: str) -> tuple[str, str, str]:
    """Discover the public client configuration used by KPMG's own career UI."""
    page = fetch(seed_url)
    soup = BeautifulSoup(page.text, "html.parser")
    loader = next(
        (
            urljoin(page.url, script.get("src"))
            for script in soup.find_all("script", src=True)
            if "csb.esm.js" in script.get("src", "")
        ),
        "",
    )
    if not loader:
        raise ValueError("KPMG public career client was not found")
    manifest = fetch(loader)
    core_match = re.search(r'from"\./([^"?]+\.js)', manifest.text)
    if not core_match:
        raise ValueError("KPMG public career client manifest changed")
    core = fetch(urljoin(manifest.url, core_match.group(1))).text
    api_url = re.search(r'apiUrl:"(https://[^"]+)"', core)
    api_key = re.search(r'apiKey:"(pk_[^"]+)"', core)
    customer_from_key = (
        re.match(r"pk_([^_]+)_", api_key.group(1)).group(1) if api_key else ""
    )
    customer_ids = re.findall(r'customerId:"([^"]+)"', core)
    customer_id = customer_from_key or next(
        (value for value in customer_ids if value.startswith("kpmg-") and len(value) > 5),
        "",
    )
    if not (api_url and customer_id and api_key):
        raise ValueError("KPMG public API configuration changed")
    return api_url.group(1), customer_id, api_key.group(1)


def discover_kpmg_api_jobs(source: pd.Series, max_jobs: int = 100) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    jobs: dict[str, dict] = {}
    try:
        api_url, customer_id, api_key = _kpmg_public_api_config(source.seed_url)
        response = requests.post(
            f"{api_url}/search",
            headers={
                **HEADERS,
                "customerId": customer_id,
                "x-api-key": api_key,
                "internal": "false",
                "privateJobBoard": "false",
                "Content-Type": "application/json",
            },
            json={
                "search": "finance",
                "searchFields": "title,description,tasks,profile,keyWords,jobTypes,jobLevels,jobFunctions",
                "top": max_jobs,
                "skip": 0,
                "count": True,
            },
            timeout=30,
        )
        response.raise_for_status()
        records = response.json().get("value", [])
    except Exception as exc:
        records = []
        errors.append(f"KPMG public jobs API: {type(exc).__name__}")

    for record in records:
        locations = []
        for address in record.get("addresses") or []:
            if isinstance(address, dict):
                locations.append(
                    {
                        "@type": "Place",
                        "address": {
                            "addressLocality": address.get("city") or "",
                            "addressRegion": address.get("state") or "",
                            "addressCountry": address.get("countryCode") or "DE",
                            "postalCode": address.get("postalCode") or "",
                        },
                    }
                )
        duties = record.get("tasks") or record.get("description") or ""
        posting = {
            "@type": "JobPosting",
            "title": record.get("title"),
            "description": duties,
            "datePosted": record.get("datePosted") or record.get("startDate"),
            "jobLocation": locations,
            "identifier": {"value": record.get("jobId")},
            "url": record.get("link"),
            "_verification": "official ATS vacancy detail",
        }
        job = posting_to_job(posting, record.get("link") or source.seed_url, source, started)
        if job:
            jobs[job["job_id"]] = job

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": 1,
        "candidate_job_pages": len(records),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def merge_jobs(new_jobs: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "job_id", "canonical_company_id", "company", "title", "description",
        "description_en", "translation_status", "market", "location",
        "priority_locations", "job_url", "source_url", "source_id", "date_posted",
        "discovered_at", "last_seen_at", "relevance_score", "matched_terms",
        "verification", "status", "alternate_job_urls", "duplicate_count",
        "calibration_score", "calibration_note",
    ]
    old = pd.read_csv(JOBS_PATH).fillna("") if JOBS_PATH.exists() else pd.DataFrame()
    if "verification" not in old.columns:
        old = pd.DataFrame(columns=columns)
    else:
        old = old.reindex(columns=columns, fill_value="")
        old = old[old["title"].map(is_real_job_title)]
    if new_jobs.empty:
        return old

    new_jobs = new_jobs.reindex(columns=columns, fill_value="").copy()
    if old.empty:
        return calibrate_jobs(new_jobs).sort_values(
            ["calibration_score", "relevance_score", "company"],
            ascending=[False, False, True],
        )

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
    combined = pd.concat([new_idx, missing]).reset_index()[columns]
    combined = calibrate_jobs(deduplicate_jobs(combined)).reindex(columns=columns, fill_value="")
    return combined.sort_values(
        ["calibration_score", "relevance_score", "last_seen_at"],
        ascending=[False, False, False],
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
        is_phenom = any(host == item or host.endswith("." + item) for item in PHENOM_HOSTS)
        has_dedicated_adapter = any(
            host == item or host.endswith("." + item) for item in SUCCESSFACTORS_HOSTS
        )
        page_limit = args.max_pages if has_dedicated_adapter else min(args.max_pages, 8)
        if is_phenom:
            jobs, run = discover_phenom_jobs(source, max_pages=min(args.max_pages, 10))
        elif host == "jobs.kpmg.de":
            jobs, run = discover_kpmg_api_jobs(source, max_jobs=100)
        else:
            jobs, run = discover_jobs(source, max_pages=page_limit)
        all_jobs.extend(jobs)
        runs.append(run)

    discovered = deduplicate_jobs(pd.DataFrame(all_jobs))
    merged = merge_jobs(translate_descriptions(discovered))
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
