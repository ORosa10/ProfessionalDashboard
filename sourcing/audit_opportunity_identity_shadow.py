"""Audit cross-source opportunity identity without merging production records.

The migration needs a canonical opportunity identity that is stronger than a
source-specific job_id but safer than fuzzy title matching. This shadow tool
therefore only *reports* high-confidence matches/conflicts; it never rewrites G,
C, J or I.

High-confidence fingerprint = normalised company core + normalised title core +
resolved country. Legal suffixes and common gender markers are ignored. Location
is deliberately not fuzzy-matched across countries.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd


LEGAL_SUFFIXES = {
    "ag", "gmbh", "se", "plc", "ltd", "limited", "inc", "incorporated",
    "corp", "corporation", "llc", "sa", "sas", "spa", "nv", "bv", "as",
    "oy", "ab", "asa", "kg", "kgaa", "co", "company", "group",
}
GENDER_MARKERS = {
    "mwd", "wmd", "mfd", "fmd", "allgenders", "gn", "dfm", "mfx", "fmx",
}
TRACKING_KEYS = {"source", "src", "ref", "referrer", "tracking", "trk", "campaign"}

REPORT_COLUMNS = [
    "reference_job_id", "reference_company", "reference_title", "reference_country",
    "match_status", "matched_job_id", "matched_candidate_id", "matched_company",
    "matched_title", "matched_country", "matched_source_streams", "matched_job_url",
    "identity_fingerprint", "notes",
]
DUP_COLUMNS = [
    "identity_fingerprint", "candidate_count", "job_ids", "companies", "titles",
    "countries", "source_streams", "job_urls",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _tokens(value: object) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(value or "").lower())


def _company_core(value: object) -> str:
    tokens = _tokens(value)
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def _title_core(value: object) -> str:
    text = str(value or "").lower()
    # Remove common slash/parenthesis gender markers without deleting substantive
    # title words such as M&A, fixed income, treasury, etc.
    compact = re.sub(r"[^a-z0-9]+", "", text)
    for marker in sorted(GENDER_MARKERS, key=len, reverse=True):
        compact = compact.replace(marker, "")
    return compact


def _country(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "UK": "United Kingdom", "GB": "United Kingdom", "United Kingdom": "United Kingdom",
        "DE": "Germany", "Germany": "Germany", "AT": "Austria", "Austria": "Austria",
        "CH": "Switzerland", "Switzerland": "Switzerland", "CZ": "Czechia", "Czechia": "Czechia",
        "SE": "Sweden", "Sweden": "Sweden", "NO": "Norway", "Norway": "Norway",
        "DK": "Denmark", "Denmark": "Denmark", "FI": "Finland", "Finland": "Finland",
    }
    return aliases.get(text, text)


def _fingerprint(company: object, title: object, country: object) -> str:
    c = _company_core(company)
    t = _title_core(title)
    k = _country(country)
    if not c or not t or not k or k in {"Other / Unresolved", "Multi-region", "Remote", "Unknown"}:
        return ""
    raw = f"{c}|{t}|{k.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _normalise_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/")
    if not parts.scheme or not parts.netloc:
        return raw.rstrip("/")
    kept = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith("utm_") or low in TRACKING_KEYS:
            continue
        kept.append((key, val))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(kept), ""))


def _unique(values: pd.Series) -> str:
    out: list[str] = []
    for value in values:
        for item in str(value or "").split(";"):
            item = item.strip()
            if item and item not in out:
                out.append(item)
    return "; ".join(out)


def _same_job_id_status(reference_company: str, reference_title: str, reference_country: str, match: pd.Series) -> tuple[str, str]:
    """Classify same-job_id metadata differences by severity.

    A company-label difference alone is common across parent/subsidiary/brand
    names and is informational. A title or country difference is a real data
    integrity conflict because the same source-specific ID should not describe a
    different vacancy.
    """
    ref_title = _title_core(reference_title)
    got_title = _title_core(match.get("title", ""))
    ref_country = _country(reference_country)
    got_country = _country(match.get("_country", ""))
    ref_company = _company_core(reference_company)
    got_company = _company_core(match.get("company", ""))

    if ref_title and got_title and ref_title != got_title:
        return "job_id_title_conflict", "Same job_id but substantive title differs. Treat as a source-data integrity problem."
    if ref_country and got_country and ref_country != got_country:
        return "job_id_country_conflict", "Same job_id but country differs. Treat as a source-data integrity problem."
    if ref_company and got_company and ref_company != got_company:
        return "job_id_company_variant", "Same job_id/title/country; company label differs and should be resolved through canonical company aliases."
    return "exact_job_id", ""


def audit_identity(candidates: pd.DataFrame, reference: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = candidates.fillna("").copy()
    for col in ["candidate_id", "job_id", "company", "title", "country_bucket", "market", "source_streams", "job_url"]:
        if col not in c.columns:
            c[col] = ""
    c["_country"] = c.apply(lambda r: _country(r.get("country_bucket", "") or r.get("market", "")), axis=1)
    c["_fp"] = c.apply(lambda r: _fingerprint(r.get("company", ""), r.get("title", ""), r.get("_country", "")), axis=1)
    c["_url"] = c["job_url"].map(_normalise_url)

    duplicates: list[dict[str, object]] = []
    for fp, group in c[c["_fp"].ne("")].groupby("_fp", sort=False):
        # Same fingerprint appearing through >1 candidate records is a potential
        # duplicate cluster, not an automatic merge instruction.
        if len(group) < 2:
            continue
        duplicates.append({
            "identity_fingerprint": fp,
            "candidate_count": len(group),
            "job_ids": _unique(group["job_id"]),
            "companies": _unique(group["company"]),
            "titles": _unique(group["title"]),
            "countries": _unique(group["_country"]),
            "source_streams": _unique(group["source_streams"]),
            "job_urls": _unique(group["job_url"]),
        })

    ref = reference.fillna("").copy()
    reports: list[dict[str, object]] = []
    for _, row in ref.iterrows():
        rid = str(row.get("job_id", row.get("opportunity_id", "")) or "").strip()
        company = str(row.get("company", "") or "").strip()
        title = str(row.get("title", "") or "").strip()
        country = _country(row.get("market", row.get("country", "")))
        fp = _fingerprint(company, title, country)
        exact = c[c["job_id"].astype(str).eq(rid)] if rid else pd.DataFrame()
        status = "missing"
        match = None
        notes = ""

        if not exact.empty:
            match = exact.iloc[0]
            status, notes = _same_job_id_status(company, title, country, match)
        elif fp:
            matches = c[c["_fp"].eq(fp)]
            if len(matches) == 1:
                match = matches.iloc[0]
                status = "high_confidence_identity_match"
                notes = "Different source-specific job_id/URL, same normalised company + title + country."
            elif len(matches) > 1:
                match = matches.iloc[0]
                status = "ambiguous_identity_cluster"
                notes = f"{len(matches)} shadow candidates share the same high-confidence fingerprint."

        if match is None:
            match = pd.Series(dtype=object)
        reports.append({
            "reference_job_id": rid,
            "reference_company": company,
            "reference_title": title,
            "reference_country": country,
            "match_status": status,
            "matched_job_id": str(match.get("job_id", "")),
            "matched_candidate_id": str(match.get("candidate_id", "")),
            "matched_company": str(match.get("company", "")),
            "matched_title": str(match.get("title", "")),
            "matched_country": str(match.get("_country", "")),
            "matched_source_streams": str(match.get("source_streams", "")),
            "matched_job_url": str(match.get("job_url", "")),
            "identity_fingerprint": fp,
            "notes": notes,
        })

    return (
        pd.DataFrame(reports).reindex(columns=REPORT_COLUMNS, fill_value=""),
        pd.DataFrame(duplicates).reindex(columns=DUP_COLUMNS, fill_value=""),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--reference-out", required=True)
    parser.add_argument("--duplicates-out", required=True)
    args = parser.parse_args()

    report, duplicates = audit_identity(_read(Path(args.candidates)), _read(Path(args.reference)))
    ref_out = Path(args.reference_out)
    dup_out = Path(args.duplicates_out)
    ref_out.parent.mkdir(parents=True, exist_ok=True)
    dup_out.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(ref_out, index=False)
    duplicates.to_csv(dup_out, index=False)
    print("identity audit statuses:")
    print(report["match_status"].value_counts().to_string() if len(report) else "none")
    print(f"potential duplicate clusters: {len(duplicates)}")


if __name__ == "__main__":
    main()
