from __future__ import annotations

import argparse
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from ddgs import DDGS

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS_PATH = ROOT / "data" / "user_submitted_opportunities.csv"
RESEARCH_PATH = ROOT / "data" / "user_submitted_opportunity_research.csv"
REQUESTS_PATH = ROOT / "data" / "salary_research_requests.csv"

REQUEST_COLUMNS = ["submission_id", "requested_at", "status", "completed_at", "message"]
RESEARCH_COLUMNS = [
    "submission_id", "title", "company", "canonical_company_id", "company_category",
    "location", "country", "topic", "role_summary_en", "company_profile", "role_profile",
    "salary_research", "salary_range", "targeting_scope", "review_status",
]

COUNTRY_CURRENCY = {
    "germany": "EUR", "austria": "EUR", "finland": "EUR", "france": "EUR",
    "netherlands": "EUR", "belgium": "EUR", "ireland": "EUR",
    "switzerland": "CHF", "united kingdom": "GBP", "uk": "GBP",
    "czechia": "CZK", "czech republic": "CZK", "sweden": "SEK",
    "norway": "NOK", "denmark": "DKK",
}
CURRENCY_SYMBOLS = {
    "€": "EUR", "eur": "EUR", "chf": "CHF", "£": "GBP", "gbp": "GBP",
    "czk": "CZK", "kč": "CZK", "sek": "SEK", "nok": "NOK", "dkk": "DKK",
}
RANGES = {
    "EUR": (30000, 350000), "GBP": (30000, 350000), "CHF": (50000, 450000),
    "CZK": (500000, 6000000), "SEK": (350000, 3000000), "NOK": (400000, 3500000),
    "DKK": (300000, 2500000),
}
ROUND_TO = {"EUR": 5000, "GBP": 5000, "CHF": 5000, "CZK": 50000, "SEK": 25000, "NOK": 25000, "DKK": 25000}

AMOUNT_RE = re.compile(
    r"(?:(€|EUR|CHF|£|GBP|CZK|Kč|SEK|NOK|DKK)\s*)"
    r"(\d{1,3}(?:[\s.,]\d{3})+|\d{2,3}(?:[.,]\d+)?\s*[kK])"
    r"|"
    r"(\d{1,3}(?:[\s.,]\d{3})+|\d{2,3}(?:[.,]\d+)?\s*[kK])\s*"
    r"(€|EUR|CHF|£|GBP|CZK|Kč|SEK|NOK|DKK)",
    flags=re.IGNORECASE,
)


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


LOCATION_COUNTRY_HINTS = {
    "baar": "Switzerland", "zug": "Switzerland", "zurich": "Switzerland",
    "zürich": "Switzerland", "basel": "Switzerland", "geneva": "Switzerland",
    "genève": "Switzerland", "lausanne": "Switzerland", "bern": "Switzerland",
    "lucerne": "Switzerland", "rorschach": "Switzerland", "winterthur": "Switzerland",
    "luxembourg": "Luxembourg", "london": "United Kingdom", "frankfurt": "Germany",
    "munich": "Germany", "münchen": "Germany", "vienna": "Austria",
    "aarhus": "Denmark", "copenhagen": "Denmark", "paris": "France",
}


def _inferred_country(row: pd.Series) -> str:
    explicit = _text(row.get("country"))
    if explicit:
        return explicit
    haystack = " ".join(
        _text(row.get(key))
        for key in ["location", "company_url", "job_url", "source_domain", "title", "company"]
    ).lower()
    for hint, country in LOCATION_COUNTRY_HINTS.items():
        if hint in haystack:
            return country
    return ""


def _expected_currency(country: str, location: str, urls: str = "") -> str:
    haystack = f"{country} {location} {urls}".lower()
    for key, currency in COUNTRY_CURRENCY.items():
        if key in haystack:
            return currency
    for hint, inferred_country in LOCATION_COUNTRY_HINTS.items():
        if hint in haystack:
            return COUNTRY_CURRENCY.get(inferred_country.lower(), "")
    return ""


def _number(value: str) -> float | None:
    raw = value.strip().lower().replace(" ", "")
    multiplier = 1000 if raw.endswith("k") else 1
    raw = raw.rstrip("k")
    # Thousands separators are far more common than decimals for salary values.
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
        raw = raw.replace(".", "").replace(",", "")
    elif raw.count(",") == 1 and raw.count(".") == 0:
        left, right = raw.split(",")
        raw = left + ("." + right if len(right) <= 2 else right)
    elif raw.count(".") == 1 and raw.count(",") == 0:
        left, right = raw.split(".")
        raw = left + ("." + right if len(right) <= 2 else right)
    else:
        raw = raw.replace(",", "").replace(".", "")
    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def _annualize(value: float, currency: str, context: str) -> float:
    lower = context.lower()
    monthly = any(term in lower for term in [
        "per month", "monthly", "/month", "pro monat", "monatlich", "měsíčně", "za měsíc",
        "per månad", "månadslön", "per måned", "månedslønn", "kuukaudessa", "per måned",
    ])
    if monthly:
        return value * 12
    if currency == "CZK" and 30000 <= value <= 300000:
        return value * 12
    return value


def _extract_values(text: str, expected_currency: str) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for match in AMOUNT_RE.finditer(text):
        symbol = match.group(1) or match.group(4) or ""
        amount_text = match.group(2) or match.group(3) or ""
        currency = CURRENCY_SYMBOLS.get(symbol.lower(), "")
        if not currency:
            continue
        if expected_currency and currency != expected_currency:
            continue
        value = _number(amount_text)
        if value is None:
            continue
        context = text[max(0, match.start() - 90): min(len(text), match.end() + 90)]
        value = _annualize(value, currency, context)
        low, high = RANGES.get(currency, (0, math.inf))
        if low <= value <= high:
            values.append((currency, value))
    return values


def _queries(row: pd.Series) -> list[str]:
    title = _text(row.get("title"))
    company = _text(row.get("company"))
    location = _text(row.get("location"))
    country = _inferred_country(row)
    query_location = location or country
    base = " ".join(x for x in [f'"{title}"' if title else "", f'"{company}"' if company else "", query_location] if x)
    generic = " ".join(x for x in [f'"{title}"' if title else "", query_location] if x)
    local_word = "salary"
    c = country.lower()
    if any(x in c for x in ["germany", "austria", "switzerland"]):
        local_word = "Gehalt"
    elif "czech" in c:
        local_word = "plat mzda"
    elif "sweden" in c:
        local_word = "lön salary"
    elif "norway" in c:
        local_word = "lønn salary"
    elif "denmark" in c:
        local_word = "løn salary"
    elif "finland" in c:
        local_word = "palkka salary"
    queries = [
        f"{base} salary compensation".strip(),
        f"{base} {local_word}".strip(),
        f"{generic} salary compensation".strip(),
        f'{base} site:kununu.com Gehalt'.strip(),
        f'{base} site:glassdoor.com salary'.strip(),
        f'{base} site:xing.com/jobs salary'.strip(),
        f'{generic} site:salaryexpert.com salary'.strip(),
    ]
    if "switzerland" in c:
        queries.append(f"{base} site:jobs.ch salary")
    elif "austria" in c:
        queries.append(f"{base} site:karriere.at Gehalt")
    elif "germany" in c:
        queries.append(f"{base} site:stepstone.de Gehalt")
    elif "united kingdom" in c or c == "uk":
        queries.append(f"{base} site:totaljobs.com salary")
    return list(dict.fromkeys(q for q in queries if q and len(q) > 8))


def _search(row: pd.Series) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    with DDGS() as ddgs:
        for query in _queries(row):
            try:
                found = ddgs.text(query, max_results=7)
            except Exception:
                continue
            for item in found or []:
                href = _text(item.get("href"))
                body = _text(item.get("body"))
                title = _text(item.get("title"))
                key = href or f"{title}|{body[:120]}"
                if not key or key in seen:
                    continue
                seen.add(key)
                results.append({"title": title, "href": href, "body": body})
                if len(results) >= 16:
                    return results
    return results


def _round(value: float, currency: str) -> int:
    step = ROUND_TO.get(currency, 5000)
    return int(round(value / step) * step)


def _format_amount(value: int, currency: str) -> str:
    if currency in {"EUR", "GBP", "CHF"}:
        return f"{currency} {value / 1000:.0f}k"
    if currency == "CZK":
        return f"CZK {value / 1_000_000:.2f}m"
    return f"{currency} {value / 1000:.0f}k"


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return ""


def research_salary(row: pd.Series) -> tuple[str, str, str]:
    inferred_country = _inferred_country(row)
    url_hints = " ".join(_text(row.get(key)) for key in ["company_url", "job_url", "source_domain"])
    expected = _expected_currency(inferred_country, _text(row.get("location")), url_hints)
    results = _search(row)
    evidence: list[tuple[str, float, dict[str, str]]] = []
    for item in results:
        combined = f"{item['title']} {item['body']}"
        for currency, value in _extract_values(combined, expected):
            evidence.append((currency, value, item))

    if not evidence:
        sources = [r["href"] for r in results[:3] if r.get("href")]
        source_text = " ; ".join(sources)
        note = "Zero-cost web search found no reliable salary figures. Needs ChatGPT review."
        if source_text:
            note += f" Search leads: {source_text}"
        return "Needs ChatGPT review", note, "needs_review"

    currency_counts: dict[str, int] = {}
    for currency, _, _ in evidence:
        currency_counts[currency] = currency_counts.get(currency, 0) + 1
    currency = expected or max(currency_counts, key=currency_counts.get)
    filtered = [(v, item) for c, v, item in evidence if c == currency]
    values = sorted(v for v, _ in filtered)
    domains = {_domain(item.get("href", "")) for _, item in filtered if _domain(item.get("href", ""))}

    # Trim obvious outliers once we have enough observations.
    if len(values) >= 5:
        q1 = values[max(0, int(len(values) * 0.2) - 1)]
        q3 = values[min(len(values) - 1, int(len(values) * 0.8))]
        values = [v for v in values if q1 * 0.7 <= v <= q3 * 1.35] or values

    if len(values) >= 3:
        low = values[max(0, int((len(values) - 1) * 0.20))]
        target = values[max(0, int((len(values) - 1) * 0.60))]
        high = values[max(0, int((len(values) - 1) * 0.80))]
    elif len(values) == 2:
        low, high = values
        target = low + (high - low) * 0.65
    else:
        target = values[0]
        low, high = target * 0.88, target * 1.12

    low_i, target_i, high_i = (_round(x, currency) for x in (low, target, high))
    if high_i <= low_i:
        high_i = low_i + ROUND_TO.get(currency, 5000) * 2
    if target_i < low_i:
        target_i = low_i
    if target_i > high_i:
        target_i = high_i

    confidence = "medium"
    if len(values) >= 4 and len(domains) >= 2:
        confidence = "good"
    elif len(values) == 1 or len(domains) <= 1:
        confidence = "low"

    salary_range = (
        f"{_format_amount(low_i, currency)}-{_format_amount(high_i, currency).replace(currency + ' ', '')} gross/year"
        f" | target ~{_format_amount(target_i, currency)}"
    )

    unique_sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for _, item in filtered:
        href = item.get("href", "")
        if href and href not in seen_urls:
            seen_urls.add(href)
            unique_sources.append(item)
        if len(unique_sources) >= 4:
            break
    source_bits = []
    for item in unique_sources:
        domain = _domain(item.get("href", "")) or item.get("title", "")
        snippet = item.get("body", "")[:220]
        source_bits.append(f"{domain}: {snippet} ({item.get('href', '')})")

    today = datetime.now(timezone.utc).date().isoformat()
    research = (
        f"ZERO-COST WEB RESEARCH ({today}, confidence: {confidence}). "
        f"Observed {len(values)} plausible {currency} salary figure(s) across {max(1, len(domains))} source domain(s). "
        f"Market indication: {_format_amount(low_i, currency)} to {_format_amount(high_i, currency)} gross/year. "
        f"Suggested target for negotiation: ~{_format_amount(target_i, currency)}; open near {_format_amount(high_i, currency)}; "
        f"treat ~{_format_amount(low_i, currency)} as the lower end before benefits/bonus. "
        f"This is a deterministic estimate from public search results, not a paid data feed. Sources: " + " | ".join(source_bits)
    )
    status = "done" if confidence in {"good", "medium"} else "needs_review"
    if status == "needs_review":
        research += " Low-confidence result: review in ChatGPT before relying on it."
    return salary_range, research, status


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path).fillna("").reindex(columns=columns, fill_value="")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)


def run(max_items: int = 10, only_submission_id: str = "") -> int:
    submissions = pd.read_csv(SUBMISSIONS_PATH).fillna("")
    requests = _load_csv(REQUESTS_PATH, REQUEST_COLUMNS)
    research = _load_csv(RESEARCH_PATH, RESEARCH_COLUMNS)

    pending = requests[requests["status"].astype(str).str.lower().isin(["queued", "pending", "retry"])].copy()
    if only_submission_id:
        pending = pending[pending["submission_id"].astype(str) == only_submission_id]
    pending = pending.sort_values("requested_at").head(max_items)
    if pending.empty:
        print("No salary research requests pending")
        return 0

    submission_map = submissions.drop_duplicates("submission_id", keep="last").set_index("submission_id")
    research_map = research.drop_duplicates("submission_id", keep="last").set_index("submission_id") if not research.empty else pd.DataFrame(columns=RESEARCH_COLUMNS).set_index(pd.Index([], name="submission_id"))

    processed = 0
    now = datetime.now(timezone.utc).isoformat()
    for req_idx, req in pending.iterrows():
        sid = _text(req.get("submission_id"))
        if sid not in submission_map.index:
            requests.loc[req_idx, ["status", "completed_at", "message"]] = ["failed", now, "Submission not found"]
            continue
        row = submission_map.loc[sid]
        try:
            salary_range, salary_research, status = research_salary(row)
        except Exception as exc:
            requests.loc[req_idx, ["status", "completed_at", "message"]] = ["failed", now, f"{type(exc).__name__}: {exc}"]
            print(f"FAILED {sid}: {exc}")
            continue

        if sid in research_map.index:
            record = research_map.loc[sid].to_dict()
        else:
            record = {col: "" for col in RESEARCH_COLUMNS if col != "submission_id"}
        for col in [
            "title", "company", "canonical_company_id", "company_category", "location", "country", "topic",
            "role_summary_en", "company_profile", "role_profile", "targeting_scope",
        ]:
            if not _text(record.get(col)):
                record[col] = _text(row.get(col))
        record["salary_range"] = salary_range
        record["salary_research"] = salary_research
        existing_status = _text(record.get("review_status"))
        if status == "done":
            record["review_status"] = existing_status or "Salary researched - zero-cost web"
        else:
            record["review_status"] = "Salary needs ChatGPT review"
        research_map.loc[sid, [c for c in RESEARCH_COLUMNS if c != "submission_id"]] = [record.get(c, "") for c in RESEARCH_COLUMNS if c != "submission_id"]

        requests.loc[req_idx, ["status", "completed_at", "message"]] = [status, now, salary_range]
        processed += 1
        print(f"SALARY {sid}: {salary_range} ({status})")

    out_research = research_map.reset_index().reindex(columns=RESEARCH_COLUMNS, fill_value="")
    out_research.to_csv(RESEARCH_PATH, index=False)
    requests.reindex(columns=REQUEST_COLUMNS, fill_value="").to_csv(REQUESTS_PATH, index=False)
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--submission-id", default="")
    args = parser.parse_args()
    count = run(args.max_items, args.submission_id)
    print(f"Processed {count} salary research request(s)")


if __name__ == "__main__":
    main()
