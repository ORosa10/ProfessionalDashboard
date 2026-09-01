from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import unicodedata
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
STAGING_JOBS_PATH = ROOT / "data" / "jobs_staging.csv"
STAGING_RUNS_PATH = ROOT / "data" / "source_runs_staging.csv"
ACTIVE_JOBS_OUTPUT_PATH = JOBS_PATH
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
    r"^open application",
    r"^spontaneous application",
    r"^åpen søknad",
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
SUCCESSFACTORS_SITEMAP_HOSTS = ("bewerbung.kpmg.at",)
PHENOM_HOSTS = ("jobs.pwc.de", "jobs.pwc.co.uk", "jobs-cee.pwc.com")
WORKDAY_HOSTS = ("pwc.wd3.myworkdayjobs.com",)
JOBYLON_HOSTS = ("cdn.jobylon.com",)
SMARTRECRUITERS_HOSTS = ("careers.smartrecruiters.com", "jobs.smartrecruiters.com")
AVATURE_HOSTS = (
    "apply.deloittece.com",
    "apply.deloitte.ch",
    "apply.deloitte.co.uk",
)
HEADERS = {
    "User-Agent": "ProfessionalDashboard/0.2 (+https://github.com/ORosa10/ProfessionalDashboard)"
}

MARKET_LOCATION_TERMS = {
    "Czechia": ("czech", "česk", "praha", "prague", "brno", "ostrava", ", cz"),
    "Germany": ("germany", "deutschland", "munich", "münchen", "berlin", "frankfurt", "hamburg", ", de"),
    "Austria": ("austria", "österreich", "vienna", "wien", ", at"),
    "Switzerland": ("switzerland", "schweiz", "zurich", "zürich", ", ch"),
    "United Kingdom": ("united kingdom", "uk", "london", "england", ", gb"),
    "Sweden": ("sweden", "stockholm", ", se"),
    "Norway": ("norway", "oslo", ", no"),
    "Denmark": ("denmark", "copenhagen", ", dk"),
    "Finland": ("finland", "helsinki", ", fi"),
    "Nordics": (
        "sweden", "stockholm", "denmark", "copenhagen", "norway", "oslo",
        "finland", "helsinki", ", se", ", dk", ", no", ", fi",
    ),
}


def due_for_check(source: pd.Series, runs_path: Path) -> bool:
    """Respect each source's rating-based cadence (data/job_sources_*.csv's
    cadence_days column: A=7d, B=14d, C=30d -- set by scripts/build_sector_sources.py)
    instead of re-checking every company's career page on every single daily
    run. A brand-new source with no prior entry in runs_path always returns
    True, so it still gets its first, initial-database-building check
    immediately rather than waiting out its cadence.

    A source whose MOST RECENT run recorded an error (e.g. a missing
    GEMINI_API_KEY secret, a timeout, a transient site outage) is also always
    due again, regardless of cadence -- we never actually managed to check
    it, so it shouldn't have to wait out a 7-30 day cooldown as if it had.
    """
    cadence_days = pd.to_numeric(source.get("cadence_days", 1), errors="coerce")
    cadence_days = 1 if pd.isna(cadence_days) else max(1, int(cadence_days))
    if not runs_path.exists():
        return True
    try:
        runs = pd.read_csv(
            runs_path, usecols=lambda c: c in ("source_id", "run_at", "errors")
        ).fillna("")
    except Exception:
        return True
    if "source_id" not in runs.columns or "run_at" not in runs.columns:
        return True
    matches = runs[runs["source_id"] == source.source_id]
    if matches.empty:
        return True
    matches = matches.assign(
        _run_at=pd.to_datetime(matches["run_at"], errors="coerce", utc=True)
    ).sort_values("_run_at")
    last_run_row = matches.iloc[-1]
    last_run = last_run_row["_run_at"]
    if pd.isna(last_run):
        return True
    if str(last_run_row.get("errors", "")).strip():
        return True
    age_days = (pd.Timestamp.now(tz="UTC") - last_run).total_seconds() / 86400
    return age_days >= cadence_days


def allowed(url: str, domains: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return any(
        host == domain.strip().lower() or host.endswith("." + domain.strip().lower())
        for domain in domains.split(";")
        if domain.strip()
    )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def searchable(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    return normalize("".join(char for char in value if not unicodedata.combining(char)).lower())


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


def is_relevant_listing_title(title: str) -> bool:
    """Keep discovery broad, but do not download every unrelated ATS vacancy."""
    low = normalize(title).lower()
    if any(term in low for term in ("talent acquisition", "recruiter", "recruiting")):
        return False
    discovery_terms = ROLE_TERMS + (
        "finance", "financial", "controller", "controlling", "cfo", "economics",
        "commercial", "business analyst", "data analyst", "due diligence",
        "banking", "pension", "actuarial", "performance management",
    )
    return is_real_job_title(title) and any(term in low for term in discovery_terms)


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


def cached_jobs_for_source(source: pd.Series) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return recent verified details by stable id and URL for incremental runs.

    Mondays deliberately bypass this cache so long-lived vacancies are fully
    refreshed at least weekly. Listings are still checked on every run, so new
    and removed requisition IDs are detected daily.
    """
    cache_path = ACTIVE_JOBS_OUTPUT_PATH if ACTIVE_JOBS_OUTPUT_PATH.exists() else JOBS_PATH
    if datetime.now(timezone.utc).weekday() == 0 or not cache_path.exists():
        return {}, {}
    old = pd.read_csv(cache_path).fillna("")
    if old.empty or "source_id" not in old.columns:
        return {}, {}
    old = old[old["source_id"].eq(str(source.source_id))]
    by_id: dict[str, dict] = {}
    by_url: dict[str, dict] = {}
    for _, row in old.iterrows():
        value = row.to_dict()
        job_id = str(value.get("job_id") or "")
        if job_id:
            by_id[job_id] = value
        urls = [value.get("job_url", "")]
        urls.extend(str(value.get("alternate_job_urls") or "").split(";"))
        for url in urls:
            url = normalize(str(url))
            if url:
                by_url[url] = value
    return by_id, by_url


def stable_job_id(source: pd.Series, external_id: str) -> str:
    return hashlib.sha1(
        f"{source.canonical_company_id}|{external_id}".encode("utf-8")
    ).hexdigest()[:16]


def reuse_cached_job(value: dict, source: pd.Series, started: str) -> dict:
    job = dict(value)
    job.update(
        {
            "source_id": source.source_id,
            "source_url": source.seed_url,
            "last_seen_at": started,
            "status": "Open",
        }
    )
    return job


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


CALIBRATION_RULES_PATH = ROOT / "data" / "calibration_rules.json"

_DEFAULT_CALIBRATION_RULES = {
    "positive_rules": {
        "transactions / M&A": {"terms": ["transaction", "m&a", "merger", "acquisition"], "weight": 10},
        "corporate finance / valuation": {"terms": ["corporate finance", "valuation", "financial model"], "weight": 10},
        "treasury / FP&A": {"terms": ["treasury", "fp&a", "financial planning", "controlling"], "weight": 10},
        "finance transformation / analytics": {"terms": ["finance transformation", "finance analytics", "data analy"], "weight": 10},
    },
    "caution_rules": {
        "junior or graduate level": {"terms": ["intern", "graduate", "entry level", "berufseinstieg", "assistant"], "weight": -14},
        "likely above target seniority": {"terms": ["director", "partner", "senior manager", "head of "], "weight": -9},
        "tax-heavy": {"terms": [" tax ", "taxation"], "weight": -9},
        "SAP-heavy": {"terms": [" sap "], "weight": -9},
        "accounting / audit-heavy": {"terms": ["accounting", "audit", "assurance", "wirtschaftspr\u00fcfung"], "weight": -9},
        "internal HR/services": {"terms": ["human resources", "recruit", "internal services"], "weight": -9},
        "forensics / compliance-heavy": {"terms": ["forensic", "compliance"], "weight": -9},
    },
}


def _load_calibration_rules() -> dict:
    """Load the learnable calibration scoring rules from data/calibration_rules.json,
    falling back to the built-in defaults if the file is missing or malformed. The
    calibration loop updates that JSON from feedback so scoring can learn without a
    code change; scoring only reorders review priority and never hard-excludes."""
    try:
        with open(CALIBRATION_RULES_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data.get("positive_rules"), dict) and isinstance(data.get("caution_rules"), dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
        pass
    return _DEFAULT_CALIBRATION_RULES


def calibrate_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    """Apply transparent, feedback-derived review ordering without hard exclusions."""
    if jobs.empty:
        return jobs
    result = jobs.copy()
    rules = _load_calibration_rules()
    positive_rules = rules["positive_rules"]
    caution_rules = rules["caution_rules"]
    scores: list[int] = []
    notes: list[str] = []
    for row in result.itertuples():
        text = f"{getattr(row, 'title', '')} {getattr(row, 'description_en', '')}".lower()
        score = 50
        positive: list[str] = []
        caution: list[str] = []
        padded = f" {text} "
        for label, rule in positive_rules.items():
            if any(term in padded for term in rule.get("terms", [])):
                positive.append(label)
                score += int(rule.get("weight", 10))
        for label, rule in caution_rules.items():
            if any(term in padded for term in rule.get("terms", [])):
                caution.append(label)
                score += int(rule.get("weight", -9))
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
    _, cached_by_url = cached_jobs_for_source(source)
    for record_id, record in records.items():
        detail_url = urlunparse(
            parsed_seed._replace(
                path=f"{detail_prefix}/job/{record_id}", query="", fragment=""
            )
        )
        if detail_url in cached_by_url:
            cached = reuse_cached_job(cached_by_url[detail_url], source, started)
            jobs[cached["job_id"]] = cached
            candidate_pages += 1
            continue
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


def avature_posting_from_soup(
    soup: BeautifulSoup, page_url: str, source: pd.Series
) -> dict | None:
    """Extract a verified vacancy from Deloitte's server-rendered Avature portals."""
    jsonld = extract_job_postings(soup, page_url)
    posting = dict(jsonld[0]) if jsonld else {}
    title_node = soup.select_one("h1")
    title = normalize(
        str(posting.get("title") or "")
        or (title_node.get_text(" ", strip=True) if title_node else "")
    )
    if not is_real_job_title(title):
        return None

    fields: dict[str, str] = {}
    for field in soup.select(".article__content__view__field"):
        label = field.select_one(".article__content__view__field__label")
        value = field.select_one(".article__content__view__field__value")
        if label and value:
            fields[normalize(label.get_text(" ", strip=True)).lower()] = normalize(
                value.get_text(" ", strip=True)
            )

    articles = soup.select("article.article--details")
    description = ""
    for article in articles:
        heading = article.find(["h2", "h3"])
        heading_text = normalize(heading.get_text(" ", strip=True) if heading else "").lower()
        body = article.select_one(".article__content__view") or article
        body_text = normalize(body.get_text(" ", strip=True))
        if (
            len(body_text) > len(description)
            and "share this job" not in heading_text
            and heading_text not in {"basic information", "general information"}
        ):
            description = body_text

    city = fields.get("city") or fields.get("location") or ""
    country = fields.get("country") or str(source.market)
    location = ", ".join(dict.fromkeys(part for part in (city, country) if part))
    identifier = re.search(r"/(\d+)(?:[/?#]|$)", page_url)
    posting.update(
        {
            "@type": "JobPosting",
            "title": title,
            "description": description,
            "datePosted": posting.get("datePosted") or fields.get("date published") or "",
            "jobLocation": {"@type": "Place", "address": location},
            "identifier": {"value": identifier.group(1) if identifier else page_url},
            "url": page_url,
            "_verification": "official Deloitte ATS vacancy detail",
        }
    )
    return posting


def discover_avature_jobs(
    source: pd.Series, max_pages: int = 40, max_jobs: int = 140
) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    queue = [source.seed_url]
    queued = set(queue)
    visited: set[str] = set()
    candidates: dict[str, tuple[int, str]] = {}
    errors: list[str] = []

    while queue and len(visited) < max_pages:
        listing_url = queue.pop(0)
        if listing_url in visited:
            continue
        visited.add(listing_url)
        try:
            response = fetch(listing_url)
        except Exception as exc:
            errors.append(f"{listing_url}: {type(exc).__name__}")
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = urljoin(response.url, anchor.get("href", ""))
            title = normalize(anchor.get_text(" ", strip=True))
            parsed = urlparse(href)
            if (
                parsed.scheme in {"http", "https"}
                and "/JobDetail/" in parsed.path
                and allowed(href, source.allowed_domains)
                and title.lower() not in {"apply now", ""}
            ):
                identifier = re.search(r"/(\d+)(?:[/?#]|$)", href)
                key = identifier.group(1) if identifier else href
                score, _ = relevance(title)
                if is_relevant_listing_title(title):
                    candidates[key] = (score, href)
            if (
                "/SearchJobs/" in parsed.path
                and "jobOffset=" in parsed.query
                and allowed(href, source.allowed_domains)
                and href not in queued
            ):
                queue.append(href)
                queued.add(href)
        time.sleep(0.15)

    jobs: dict[str, dict] = {}
    cached_by_id, cached_by_url = cached_jobs_for_source(source)
    ordered = sorted(
        candidates.items(), key=lambda item: (-item[1][0], item[1][1])
    )[:max_jobs]
    for candidate_id, (_, detail_url) in ordered:
        cached = cached_by_id.get(stable_job_id(source, candidate_id)) or cached_by_url.get(
            detail_url
        )
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        try:
            response = fetch(detail_url)
            posting = avature_posting_from_soup(
                BeautifulSoup(response.text, "html.parser"), response.url, source
            )
            job = posting_to_job(posting, response.url, source, started) if posting else None
            if job:
                jobs[job["job_id"]] = job
        except Exception as exc:
            errors.append(f"{detail_url}: {type(exc).__name__}")
        time.sleep(0.15)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": len(visited) + len(ordered),
        "candidate_job_pages": len(ordered),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def _smartrecruiters_company(seed_url: str) -> str:
    path = urlparse(seed_url).path.strip("/")
    return path.split("/", 1)[0].split("?", 1)[0]


def discover_smartrecruiters_jobs(
    source: pd.Series, max_jobs: int = 140
) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    company_slug = _smartrecruiters_company(source.seed_url)
    errors: list[str] = []
    records: list[dict] = []
    offset = 0
    total = 1
    while offset < total:
        try:
            response = fetch(
                f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings"
                f"?limit=100&offset={offset}"
            )
            payload = response.json()
            batch = payload.get("content") or []
            records.extend(batch)
            total = int(payload.get("totalFound") or len(records))
            if not batch:
                break
            offset += len(batch)
        except Exception as exc:
            errors.append(f"SmartRecruiters listing: {type(exc).__name__}")
            break

    candidates = [record for record in records if is_relevant_listing_title(record.get("name", ""))]
    candidates.sort(key=lambda record: (-relevance(record.get("name", ""))[0], record.get("name", "")))
    jobs: dict[str, dict] = {}
    cached_by_id, _ = cached_jobs_for_source(source)
    for record in candidates[:max_jobs]:
        record_id = str(record.get("id") or "")
        cached = cached_by_id.get(stable_job_id(source, record_id))
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        try:
            detail = fetch(
                f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings/{record_id}"
            ).json()
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            description_parts = []
            for section_name in ("jobDescription", "qualifications"):
                section = sections.get(section_name) or {}
                if section.get("text"):
                    description_parts.append(section["text"])
            location = detail.get("location") or {}
            posting = {
                "@type": "JobPosting",
                "title": detail.get("name"),
                "description": " ".join(description_parts),
                "datePosted": detail.get("releasedDate"),
                "jobLocation": {
                    "@type": "Place",
                    "address": location.get("fullLocation") or location.get("city") or "",
                },
                "identifier": {"value": record_id},
                "url": detail.get("postingUrl") or record.get("ref"),
                "_verification": "official SmartRecruiters vacancy API",
            }
            job = posting_to_job(posting, posting["url"] or source.seed_url, source, started)
            if job:
                jobs[job["job_id"]] = job
        except Exception as exc:
            errors.append(f"SmartRecruiters {record_id}: {type(exc).__name__}")
        time.sleep(0.1)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": 1 + min(len(candidates), max_jobs),
        "candidate_job_pages": min(len(candidates), max_jobs),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def _workday_config(seed_url: str) -> tuple[str, str, str]:
    parsed = urlparse(seed_url)
    tenant = parsed.netloc.split(".", 1)[0]
    path_parts = [part for part in parsed.path.split("/") if part]
    site = next(
        (part for part in reversed(path_parts) if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", part)),
        "",
    )
    if not tenant or not site:
        raise ValueError("Workday tenant or career site is missing")
    api_root = f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{tenant}/{site}"
    return tenant, site, api_root


def extract_jobylon_records(html_text: str) -> list[dict]:
    records: list[dict] = []
    pattern = r"\{\s*id:\s*'(\d+)'(?P<body>.*?)(?=\s*\},\s*(?:\{\s*id:|\]))"
    for match in re.finditer(pattern, html_text, re.S):
        body = match.group("body")

        def field(name: str) -> str:
            value = re.search(rf"\b{name}:\s*'((?:\\.|[^'])*)'", body, re.S)
            if not value:
                return ""
            raw = value.group(1)
            try:
                return json.loads(f'"{raw}"')
            except json.JSONDecodeError:
                return raw

        records.append(
            {
                "id": match.group(1),
                "url": field("url"),
                "title": field("title"),
                "locations_text": field("locations_text"),
                "published_date": field("published_date"),
            }
        )
    return records


def discover_jobylon_jobs(source: pd.Series, max_jobs: int = 120) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    try:
        response = fetch(source.seed_url)
        records = extract_jobylon_records(response.text)
    except Exception as exc:
        records = []
        errors.append(f"Jobylon listing: {type(exc).__name__}")

    candidates = [record for record in records if is_relevant_listing_title(record["title"])]
    candidates.sort(key=lambda record: (-relevance(record["title"])[0], record["title"]))
    jobs: dict[str, dict] = {}
    cached_by_id, cached_by_url = cached_jobs_for_source(source)
    for record in candidates[:max_jobs]:
        record_id = record["id"]
        detail_url = urljoin("https://emp.jobylon.com", record["url"])
        cached = cached_by_id.get(stable_job_id(source, record_id)) or cached_by_url.get(detail_url)
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        try:
            detail_response = fetch(detail_url)
            postings = extract_job_postings(
                BeautifulSoup(detail_response.text, "html.parser"), detail_response.url
            )
            for posting in postings:
                posting.setdefault("identifier", {"value": record_id})
                posting.setdefault("url", detail_response.url)
                if not posting.get("jobLocation"):
                    posting["jobLocation"] = {
                        "@type": "Place", "address": record["locations_text"]
                    }
                job = posting_to_job(posting, detail_response.url, source, started)
                if job:
                    jobs[job["job_id"]] = job
            # Some Jobylon pages expose a valid listing but omit schema.org
            # data on the detail page. Preserve the official listing as a
            # verified fallback instead of silently converting the source to
            # zero jobs.
            if not postings and record.get("title"):
                posting = {
                    "@type": "JobPosting",
                    "title": record["title"],
                    "description": "",
                    "datePosted": record.get("published_date") or "",
                    "jobLocation": {"@type": "Place", "address": record.get("locations_text") or ""},
                    "identifier": {"value": record_id},
                    "url": detail_response.url,
                    "_verification": "official Jobylon vacancy listing",
                }
                job = posting_to_job(posting, detail_response.url, source, started)
                if job:
                    jobs[job["job_id"]] = job
        except Exception as exc:
            errors.append(f"Jobylon {record_id}: {type(exc).__name__}")
        time.sleep(0.08)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": 1 + min(len(candidates), max_jobs),
        "candidate_job_pages": min(len(candidates), max_jobs),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def _workday_location_values(payload: dict) -> list[dict]:
    values: list[dict] = []

    def visit(value) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("facetParameter") == "locations":
            visit(value.get("values") or [])
            return
        if value.get("id") and value.get("descriptor"):
            values.append(value)
        visit(value.get("values") or [])
        visit(value.get("facets") or [])

    visit(payload.get("facets") or [])
    return values


def _workday_target_location_ids(payload: dict, source: pd.Series) -> list[str]:
    targets = [searchable(value) for value in str(source.priority_locations).split(";") if value.strip()]
    matches: list[str] = []
    for value in _workday_location_values(payload):
        descriptor = searchable(value.get("descriptor"))
        if any(target in descriptor or descriptor in target for target in targets):
            matches.append(str(value["id"]))
    return list(dict.fromkeys(matches))


def discover_workday_jobs(
    source: pd.Series, max_pages: int = 20, max_jobs: int = 140
) -> tuple[list[dict], dict]:
    """Read verified vacancies from Workday's public career-site API."""
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    records: dict[str, dict] = {}
    pages_checked = 0
    try:
        _, _, api_root = _workday_config(source.seed_url)
        facet_response = requests.post(
            f"{api_root}/jobs",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
            timeout=30,
        )
        facet_response.raise_for_status()
        facet_payload = facet_response.json()
        location_ids = _workday_target_location_ids(facet_payload, source)
        # Some shared Workday tenants expose only a subset of location facets
        # for a country. Fall back to an unfiltered listing and let the
        # verified vacancy location be matched by posting_to_job().

        search_terms = ("finance", "treasury", "transaction", "investment", "risk", "analytics")
        for search_text in search_terms:
            offset = 0
            for _ in range(max_pages):
                response = requests.post(
                    f"{api_root}/jobs",
                    headers={**HEADERS, "Content-Type": "application/json"},
                    json={
                        "appliedFacets": {"locations": location_ids} if location_ids else {},
                        "limit": 20,
                        "offset": offset,
                        "searchText": search_text,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                batch = payload.get("jobPostings") or []
                pages_checked += 1
                for record in batch:
                    external_path = normalize(str(record.get("externalPath") or ""))
                    title = normalize(str(record.get("title") or ""))
                    if external_path and is_relevant_listing_title(title):
                        records[external_path] = record
                offset += len(batch)
                if not batch or offset >= int(payload.get("total") or 0):
                    break
                time.sleep(0.08)
    except Exception as exc:
        errors.append(f"Workday listing: {type(exc).__name__}: {exc}")
        api_root = ""

    ranked = sorted(
        records.items(), key=lambda item: (-relevance(item[1].get("title", ""))[0], item[0])
    )[:max_jobs]
    jobs: dict[str, dict] = {}
    cached_by_id, cached_by_url = cached_jobs_for_source(source)
    for external_path, record in ranked:
        record_id = external_path.rstrip("/").rsplit("/", 1)[-1]
        cached = cached_by_id.get(stable_job_id(source, record_id))
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        try:
            detail_response = fetch(f"{api_root}{external_path}")
            info = detail_response.json().get("jobPostingInfo") or {}
            record_id = normalize(str(info.get("jobReqId") or info.get("id") or record_id))
            public_url = normalize(str(info.get("externalUrl") or ""))
            cached = cached_by_id.get(stable_job_id(source, record_id)) or cached_by_url.get(public_url)
            if cached:
                refreshed = reuse_cached_job(cached, source, started)
                jobs[refreshed["job_id"]] = refreshed
                continue
            country = info.get("country") or {}
            country_text = country.get("descriptor") if isinstance(country, dict) else country
            location = normalize(
                str(info.get("location") or info.get("jobRequisitionLocation") or country_text or "")
            )
            posting = {
                "@type": "JobPosting",
                "title": info.get("title") or record.get("title"),
                "description": info.get("jobDescription") or "",
                "datePosted": info.get("postedOn") or info.get("startDate") or "",
                "jobLocation": {"@type": "Place", "address": location},
                "identifier": {"value": record_id},
                "url": public_url or urljoin(source.seed_url, external_path),
                "_verification": "official Workday vacancy API",
            }
            job = posting_to_job(posting, posting["url"], source, started)
            if job:
                jobs[job["job_id"]] = job
        except Exception as exc:
            errors.append(f"Workday {record_id}: {type(exc).__name__}")
        time.sleep(0.08)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": pages_checked + len(ranked),
        "candidate_job_pages": len(ranked),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def discover_kpmg_uk_jobs(
    source: pd.Series, max_pages: int = 40, max_jobs: int = 140
) -> tuple[list[dict], dict]:
    """Read KPMG UK's server-rendered experienced-hire vacancy portal."""
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    candidates: dict[str, tuple[int, str, str]] = {}
    pages_checked = 0
    page_count = 1

    page = 1
    while page <= min(page_count, max_pages):
        listing_url = source.seed_url
        parsed = urlparse(listing_url)
        query = dict(parse_qsl(parsed.query))
        query.update({"intakeType": "Experienced", "page": str(page)})
        listing_url = urlunparse(parsed._replace(query=urlencode(query)))
        try:
            response = fetch(listing_url)
            soup = BeautifulSoup(response.text, "html.parser")
            pages_checked += 1
        except Exception as exc:
            errors.append(f"KPMG UK page {page}: {type(exc).__name__}")
            page += 1
            continue

        pagination = [
            int(match.group(1))
            for anchor in soup.select('a[href*="page="]')
            if (match := re.search(r"[?&]page=(\d+)", anchor.get("href", "")))
        ]
        if pagination:
            page_count = min(max(pagination), max_pages)

        for card in soup.select(".vacancy-result"):
            title_node = card.select_one("h3")
            link = card.select_one('a[href*="/Vacancies/"]')
            title = normalize(title_node.get_text(" ", strip=True) if title_node else "")
            if not link or not is_relevant_listing_title(title):
                continue
            detail_url = urljoin(response.url, link.get("href", ""))
            identifier = re.search(r"/(\d+)(?:[/?#]|$)", detail_url)
            if not identifier:
                continue
            score, _ = relevance(title)
            candidates[identifier.group(1)] = (score, title, detail_url)
        time.sleep(0.1)
        page += 1

    jobs: dict[str, dict] = {}
    cached_by_id, cached_by_url = cached_jobs_for_source(source)
    ranked = sorted(candidates.items(), key=lambda item: (-item[1][0], item[1][1]))[:max_jobs]
    for record_id, (_, listing_title, detail_url) in ranked:
        cached = cached_by_id.get(stable_job_id(source, record_id)) or cached_by_url.get(detail_url)
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        try:
            response = fetch(detail_url)
            soup = BeautifulSoup(response.text, "html.parser")
            title_node = soup.select_one("h1")
            description_node = soup.select_one(".job-description")
            location_node = soup.select_one(".vacancy-location")
            if not location_node:
                label = soup.find(string=re.compile(r"^\s*Location:\s*", re.I))
                location_node = label.parent if label else None
            title = normalize(title_node.get_text(" ", strip=True) if title_node else listing_title)
            location = normalize(location_node.get_text(" ", strip=True) if location_node else "")
            location = re.sub(r"^Location:\s*", "", location, flags=re.I)
            posting = {
                "@type": "JobPosting",
                "title": title,
                "description": description_node.get_text(" ", strip=True) if description_node else "",
                "jobLocation": {"@type": "Place", "address": location or "United Kingdom"},
                "identifier": {"value": record_id},
                "url": response.url,
                "_verification": "official KPMG UK vacancy detail",
            }
            job = posting_to_job(posting, response.url, source, started)
            if job:
                jobs[job["job_id"]] = job
        except Exception as exc:
            errors.append(f"KPMG UK {record_id}: {type(exc).__name__}")
        time.sleep(0.1)

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": pages_checked + len(ranked),
        "candidate_job_pages": len(ranked),
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run


def discover_kpmg_ch_jobs(source: pd.Series, max_jobs: int = 120) -> tuple[list[dict], dict]:
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    api_url = "https://ohws.prospective.ch/public/v1/medium/1693/jobs"
    try:
        response = requests.get(
            api_url, params={"lang": "en", "offset": 0, "limit": 96}, headers=HEADERS, timeout=30
        )
        response.raise_for_status()
        records = response.json().get("jobs") or []
    except Exception as exc:
        records = []
        errors.append(f"KPMG Switzerland API: {type(exc).__name__}")

    candidates = [record for record in records if is_relevant_listing_title(record.get("title", ""))]
    candidates.sort(key=lambda record: (-relevance(record.get("title", ""))[0], record.get("title", "")))
    jobs: dict[str, dict] = {}
    cached_by_id, _ = cached_jobs_for_source(source)
    for record in candidates[:max_jobs]:
        record_id = str(record.get("id") or record.get("hk_id") or "")
        cached = cached_by_id.get(stable_job_id(source, record_id))
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        szas = record.get("szas") or {}
        attributes = record.get("attributes") or {}
        description = " ".join(
            str(value)
            for value in (
                szas.get("sza_tasks"), szas.get("sza_requirements"),
                (attributes.get("60") or [""])[0],
                f"Language requirements: {szas.get('sza_language_requirements', '')}",
            )
            if value
        )
        location = szas.get("sza_location.city") or szas.get("sza_location.2.city") or "Switzerland"
        posting = {
            "@type": "JobPosting",
            "title": record.get("title"),
            "description": description,
            "datePosted": record.get("start_date") or record.get("last_modification_timestamp"),
            "jobLocation": {"@type": "Place", "address": f"{location}, Switzerland"},
            "identifier": {"value": record_id},
            "url": (record.get("links") or {}).get("directlink") or source.seed_url,
            "_verification": "official KPMG Switzerland vacancy API",
        }
        job = posting_to_job(posting, posting["url"], source, started)
        if job:
            jobs[job["job_id"]] = job

    run = {
        "run_at": started, "source_id": source.source_id, "company": source.company,
        "market": source.market, "seed_url": source.seed_url, "pages_checked": 1,
        "candidate_job_pages": len(candidates), "verified_jobs": len(jobs),
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
    _, cached_by_url = cached_jobs_for_source(source)
    for _, url in candidates[:max_jobs]:
        if url in cached_by_url:
            cached = reuse_cached_job(cached_by_url[url], source, started)
            jobs[cached["job_id"]] = cached
            candidate_pages += 1
            continue
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


KPMG_CZ_LIST_QUERY = """
query($widgetId: ID!, $page: Int, $filters: [JobAdFilter!]!, $useExampleData: Boolean!, $host: String, $version: String) {
  widget(id: $widgetId, version: $version, useExampleData: $useExampleData, host: $host) {
    jobAdList(page: $page, filters: $filters) {
      groupedJobAds {
        jobAds { id title validFrom teaser locations { country city region } }
        groups { jobAds { id title validFrom teaser locations { country city region } } }
      }
      paginator { currentPage lastPage totalNumberOfItems }
    }
  }
}
"""


def discover_kpmg_cz_jobs(source: pd.Series, max_jobs: int = 250) -> tuple[list[dict], dict]:
    """Read KPMG Czechia's public Alma Career widget instead of its HTML shell."""
    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    records: list[dict] = []
    try:
        response = requests.post(
            "https://api.capybara.lmc.cz/api/graphql/widget",
            headers={**HEADERS, "X-API-KEY": "5507a25a7131e7bdf88907199221eb7f2c82032607a6f73431aee9fd741a4489", "Content-Type": "application/json"},
            json={"query": KPMG_CZ_LIST_QUERY, "variables": {"widgetId": "9861cb46-232c-4cff-9f81-6f861835bbc9", "page": 1, "filters": [], "useExampleData": False, "host": "kpmg.jobs.cz", "version": "3"}},
            timeout=30,
        )
        response.raise_for_status()
        listing = (((response.json().get("data") or {}).get("widget") or {}).get("jobAdList") or {})
        grouped = listing.get("groupedJobAds") or {}
        open_roles = int((listing.get("paginator") or {}).get("totalNumberOfItems") or 0)

        def collect(group: dict) -> None:
            records.extend(group.get("jobAds") or [])
            for child in group.get("groups") or []:
                if isinstance(child, dict):
                    collect(child)

        collect(grouped)
    except Exception as exc:
        errors.append(f"KPMG Czechia widget API: {type(exc).__name__}")

    jobs: dict[str, dict] = {}
    cached_by_id, _ = cached_jobs_for_source(source)
    for record in records[:max_jobs]:
        record_id = str(record.get("id") or "")
        title = normalize(record.get("title", ""))
        if not record_id or not is_relevant_listing_title(title):
            continue
        cached = cached_by_id.get(stable_job_id(source, record_id))
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
        location = " · ".join(normalize(str(value)) for item in (record.get("locations") or []) for value in (item.get("city"), item.get("region"), item.get("country")) if value)
        detail_url = f"https://kpmg.jobs.cz/detail-pozice?id={record_id}"
        posting = {"@type": "JobPosting", "title": title, "description": record.get("teaser") or "", "datePosted": record.get("validFrom"), "jobLocation": {"@type": "Place", "address": location}, "identifier": {"value": record_id}, "url": detail_url, "_verification": "official KPMG Czechia vacancy widget API"}
        job = posting_to_job(posting, detail_url, source, started)
        if job:
            jobs[job["job_id"]] = job

    run = {"run_at": started, "source_id": source.source_id, "company": source.company, "market": source.market, "seed_url": source.seed_url, "pages_checked": 1, "candidate_job_pages": len(records), "open_roles": open_roles, "verified_jobs": len(jobs), "errors": " | ".join(errors[:5])}
    return list(jobs.values()), run


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

    cached_by_id, _ = cached_jobs_for_source(source)
    for record in records:
        record_id = str(record.get("jobId") or "")
        cached = cached_by_id.get(stable_job_id(source, record_id))
        if cached:
            refreshed = reuse_cached_job(cached, source, started)
            jobs[refreshed["job_id"]] = refreshed
            continue
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


def merge_jobs(new_jobs: pd.DataFrame, base_path: Path | None = None) -> pd.DataFrame:
    columns = [
        "job_id", "canonical_company_id", "company", "title", "description",
        "description_en", "translation_status", "market", "location",
        "priority_locations", "job_url", "source_url", "source_id", "date_posted",
        "discovered_at", "last_seen_at", "relevance_score", "matched_terms",
        "verification", "status", "alternate_job_urls", "duplicate_count",
        "calibration_score", "calibration_note",
    ]
    base_path = base_path or JOBS_PATH
    old = pd.read_csv(base_path).fillna("") if base_path.exists() else pd.DataFrame()
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
    global ACTIVE_JOBS_OUTPUT_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument(
        "--staging",
        action="store_true",
        help="Write a reviewable staging snapshot without changing the live app dataset.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Run only the selected source id; may be supplied more than once.",
    )
    args = parser.parse_args()
    output_jobs_path = STAGING_JOBS_PATH if args.staging else JOBS_PATH
    output_runs_path = STAGING_RUNS_PATH if args.staging else RUNS_PATH
    ACTIVE_JOBS_OUTPUT_PATH = output_jobs_path
    sources = pd.read_csv(SOURCES_PATH).fillna("")
    sources = sources[sources["enabled"].astype(str).str.lower().eq("true")]
    if args.source_id:
        sources = sources[sources["source_id"].isin(args.source_id)]
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
        elif host in WORKDAY_HOSTS:
            jobs, run = discover_workday_jobs(source, max_pages=min(args.max_pages, 20))
        elif host in JOBYLON_HOSTS:
            jobs, run = discover_jobylon_jobs(source)
        elif host in SUCCESSFACTORS_SITEMAP_HOSTS:
            jobs, run = discover_successfactors_sitemap_jobs(source, max_jobs=100)
        elif host == "www.kpmgcareers.co.uk":
            jobs, run = discover_kpmg_uk_jobs(source, max_pages=args.max_pages)
        elif host == "jobs.kpmg.ch":
            jobs, run = discover_kpmg_ch_jobs(source)
        elif host in SMARTRECRUITERS_HOSTS:
            jobs, run = discover_smartrecruiters_jobs(source, max_jobs=140)
        elif host in AVATURE_HOSTS:
            jobs, run = discover_avature_jobs(source, max_pages=args.max_pages, max_jobs=140)
        elif host == "jobs.kpmg.de":
            jobs, run = discover_kpmg_api_jobs(source, max_jobs=100)
        elif host == "kpmg.jobs.cz":
            jobs, run = discover_kpmg_cz_jobs(source, max_jobs=250)
        else:
            jobs, run = discover_jobs(source, max_pages=page_limit)
        all_jobs.extend(jobs)
        # A zero-result source is not a successful check. Dynamic career
        # boards often return an empty shell when their widget/API changes;
        # surface that condition explicitly so it cannot silently shrink the
        # next inventory or overwrite a previously healthy source state.
        if not jobs and not run.get("errors"):
            run["errors"] = "No verified postings returned; source requires review"
        runs.append(run)

    discovered = deduplicate_jobs(pd.DataFrame(all_jobs))
    base_jobs_path = output_jobs_path if output_jobs_path.exists() else JOBS_PATH
    merged = merge_jobs(translate_descriptions(discovered), base_path=base_jobs_path)
    output_jobs_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_jobs_path, index=False)

    run_df = pd.DataFrame(runs)
    base_runs_path = output_runs_path if output_runs_path.exists() else RUNS_PATH
    if base_runs_path.exists():
        history = pd.read_csv(base_runs_path).fillna("")
        run_df = pd.concat([history, run_df], ignore_index=True).tail(2000)
    run_df.to_csv(output_runs_path, index=False)
    print(
        f"Checked {len(sources)} sources; stored {len(merged)} verified jobs "
        f"in {'staging' if args.staging else 'live'}; "
        f"verified {len(all_jobs)} postings this run."
    )


if __name__ == "__main__":
    main()
