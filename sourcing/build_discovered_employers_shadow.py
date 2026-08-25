"""Prepare new-employer/alias evidence for A without assigning preference.

G and B can discover employers that A does not yet know. This shadow utility
compares those observations with the current company universe and produces
reviewable employer candidates only. Every output remains Unrated; no A/B/C/
Exclude preference is inferred from the existence or quality of a job posting.

Board-derived company labels are noisy, so the output also distinguishes obvious
UI placeholders and likely recruitment intermediaries. Those records are useful
for source-quality diagnostics but must not become A companies automatically.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


OUT_COLUMNS = [
    "discovery_key", "observed_company", "observed_canonical_company_id",
    "discovery_status", "possible_existing_company_id", "possible_existing_company",
    "source_streams", "observation_count", "markets", "example_title",
    "example_job_url", "observed_domain", "suggested_initial_rating", "notes",
]

LEGAL_SUFFIXES = {
    "ag", "gmbh", "se", "plc", "ltd", "limited", "inc", "corp", "corporation",
    "llc", "sa", "sas", "spa", "nv", "bv", "as", "oy", "ab", "asa", "kg",
    "kgaa", "co", "company", "group", "holding", "holdings",
}
NAME_NOISE = LEGAL_SUFFIXES | {
    "the", "global", "international", "deutschland", "germany", "austria",
    "osterreich", "switzerland", "schweiz", "sweden", "denmark", "norway",
    "finland", "uk", "cz", "ch", "de", "at", "se", "dk", "no", "fi",
}
INVALID_LABEL_PATTERNS = (
    r"^employer not stated$",
    r"^company not (?:stated|disclosed)$",
    r"^confidential(?: employer)?$",
    r"^unknown employer$",
    r"^poslat nabidku(?: na e mail)?$",
    r"^nabidka pracovni nabidka o nas volna mista(?: \d+)?$",
    r"^pracovni nabidka$",
    r"^volna mista(?: \d+)?$",
)
INTERMEDIARY_PATTERNS = (
    r"\brecruit(?:ment|ing)?\b",
    r"\bstaffing\b",
    r"\bheadhunt(?:er|ing)?\b",
    r"\bpersonalberatung\b",
    r"\bpersonalvermittlung\b",
)
KNOWN_INTERMEDIARY_CORES = {
    "adecco", "hays", "michaelpage", "roberthalf", "randstad", "lorien",
    "hunterbond", "workwise", "schulmeistermanagementconsulting", "consultpepper",
}


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _ascii(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _tokens(value: object) -> list[str]:
    return re.findall(r"[a-z0-9]+", _ascii(value))


def _norm(value: object) -> str:
    return "".join(_tokens(value))


def _company_tokens(value: object) -> list[str]:
    return [token for token in _tokens(value) if token not in NAME_NOISE]


def _company_core(value: object) -> str:
    tokens = _tokens(value)
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def _unique_join(values: pd.Series) -> str:
    out: list[str] = []
    for value in values:
        for item in re.split(r"[;|]", str(value or "")):
            item = item.strip()
            if item and item not in out:
                out.append(item)
    return "; ".join(out)


def _universe_maps(universes: list[pd.DataFrame]) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, list[dict]], list[dict]]:
    frames = [frame.fillna("") for frame in universes if not frame.empty]
    if not frames:
        return {}, {}, {}, []
    u = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    if "canonical_company_id" not in u.columns:
        u["canonical_company_id"] = ""
    u = u[u["canonical_company_id"].astype(str).str.strip().ne("")].drop_duplicates("canonical_company_id", keep="last")

    by_id: dict[str, dict] = {}
    exact_names: dict[str, list[dict]] = {}
    cores: dict[str, list[dict]] = {}
    all_name_records: list[dict] = []
    for _, row in u.iterrows():
        rec = row.to_dict()
        cid = str(rec.get("canonical_company_id", "")).strip()
        by_id[cid] = rec
        names = [rec.get("company", ""), *str(rec.get("aliases_entities", "")).split(";")]
        for name in names:
            if not str(name).strip():
                continue
            n = _norm(name)
            c = _company_core(name)
            if n:
                exact_names.setdefault(n, []).append(rec)
            if c:
                cores.setdefault(c, []).append(rec)
            all_name_records.append({"rec": rec, "tokens": set(_company_tokens(name))})
    return by_id, exact_names, cores, all_name_records


def _observations(candidates: pd.DataFrame, submissions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    if not candidates.empty:
        for _, row in candidates.fillna("").iterrows():
            company = str(row.get("company", "")).strip()
            if not company:
                continue
            rows.append({
                "company": company,
                "canonical_company_id": str(row.get("canonical_company_id", "")).strip(),
                "source_streams": str(row.get("source_streams", "G") or "G"),
                "market": str(row.get("country_bucket", row.get("market", ""))).strip(),
                "title": str(row.get("title", "")).strip(),
                "job_url": str(row.get("job_url", "")).strip(),
            })
    if not submissions.empty:
        for _, row in submissions.fillna("").iterrows():
            company = str(row.get("company", "")).strip()
            if not company:
                continue
            rows.append({
                "company": company,
                "canonical_company_id": str(row.get("canonical_company_id", "")).strip(),
                "source_streams": "B",
                "market": str(row.get("country", "")).strip(),
                "title": str(row.get("title", "")).strip(),
                "job_url": str(row.get("job_url", row.get("company_url", ""))).strip(),
            })
    return pd.DataFrame(rows)


def _label_quality(company: str, source_streams: str) -> tuple[str, str] | None:
    normal = " ".join(_tokens(company))
    if any(re.fullmatch(pattern, normal) for pattern in INVALID_LABEL_PATTERNS):
        return "invalid_company_label", "Board/source UI placeholder, not an employer identity."

    # Only treat a label as intermediary when it came exclusively through
    # automated sourcing. A manually submitted B role is never silently
    # downgraded by this heuristic.
    streams = {x.strip() for x in str(source_streams or "").split(";") if x.strip()}
    core = _company_core(company)
    if "B" not in streams and (
        core in KNOWN_INTERMEDIARY_CORES
        or any(re.search(pattern, normal) for pattern in INTERMEDIARY_PATTERNS)
    ):
        return "needs_employer_resolution", "Likely recruitment/intermediary label; resolve the underlying employer before adding to A."
    return None


def _fuzzy_existing(company: str, all_name_records: list[dict]) -> list[dict]:
    observed = set(_company_tokens(company))
    if not observed:
        return []
    scored: list[tuple[float, dict]] = []
    for item in all_name_records:
        tokens = item["tokens"]
        if not tokens:
            continue
        intersection = len(observed & tokens)
        if intersection == 0:
            continue
        containment = intersection / min(len(observed), len(tokens))
        jaccard = intersection / len(observed | tokens)
        # Conservative: one side must be almost contained in the other and at
        # least half the combined distinctive tokens should overlap. This is
        # only an alias suggestion, never an automatic merge.
        if containment >= 0.80 and jaccard >= 0.50:
            scored.append((jaccard, item["rec"]))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [rec for score, rec in scored if abs(score - best) < 1e-9]


def build_discovered_employers(candidates: pd.DataFrame, submissions: pd.DataFrame, universes: list[pd.DataFrame]) -> pd.DataFrame:
    obs = _observations(candidates, submissions)
    if obs.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)
    by_id, exact_names, cores, all_name_records = _universe_maps(universes)

    obs["_key"] = obs.apply(
        lambda r: f"id:{str(r.get('canonical_company_id', '')).strip()}"
        if str(r.get("canonical_company_id", "")).strip()
        else f"name:{_company_core(r.get('company', '')) or _norm(r.get('company', ''))}",
        axis=1,
    )

    rows: list[dict[str, object]] = []
    for key, group in obs.groupby("_key", sort=False):
        first = group.iloc[0]
        observed_company = str(first.get("company", ""))
        observed_id = str(first.get("canonical_company_id", ""))
        source_streams = _unique_join(group["source_streams"])
        status = "new_company_candidate"
        possible_id = ""
        possible_company = ""
        notes = "Not present in A universe; review identity/category only. Preference remains Unrated."

        if observed_id and observed_id in by_id:
            continue

        quality = _label_quality(observed_company, source_streams)
        if quality:
            status, notes = quality
        else:
            exact = exact_names.get(_norm(observed_company), [])
            core = cores.get(_company_core(observed_company), [])
            matches = exact or core or _fuzzy_existing(observed_company, all_name_records)
            unique_ids = {str(x.get("canonical_company_id", "")) for x in matches if str(x.get("canonical_company_id", ""))}
            if len(unique_ids) == 1:
                rec = next(x for x in matches if str(x.get("canonical_company_id", "")) in unique_ids)
                possible_id = str(rec.get("canonical_company_id", ""))
                possible_company = str(rec.get("company", ""))
                status = "possible_alias_of_existing"
                notes = "Observed label likely maps to an existing A company; review as alias, not a new preference record."
            elif len(unique_ids) > 1:
                status = "ambiguous_existing_identity"
                notes = "Observed label could map to multiple existing A companies; manual identity resolution needed."

        job_url = next((str(x).strip() for x in group["job_url"] if str(x).strip()), "")
        domain = (urlparse(job_url).hostname or "") if job_url else ""
        rows.append({
            "discovery_key": key,
            "observed_company": observed_company,
            "observed_canonical_company_id": observed_id,
            "discovery_status": status,
            "possible_existing_company_id": possible_id,
            "possible_existing_company": possible_company,
            "source_streams": source_streams,
            "observation_count": len(group),
            "markets": _unique_join(group["market"]),
            "example_title": next((str(x).strip() for x in group["title"] if str(x).strip()), ""),
            "example_job_url": job_url,
            "observed_domain": domain,
            "suggested_initial_rating": "Unrated",
            "notes": notes,
        })
    out = pd.DataFrame(rows).reindex(columns=OUT_COLUMNS, fill_value="").fillna("")
    if out.empty:
        return out
    status_order = {
        "possible_alias_of_existing": 0,
        "ambiguous_existing_identity": 1,
        "new_company_candidate": 2,
        "needs_employer_resolution": 3,
        "invalid_company_label": 4,
    }
    out["_status_order"] = out["discovery_status"].map(status_order).fillna(9)
    return out.sort_values(["_status_order", "observation_count", "observed_company"], ascending=[True, False, True]).drop(columns="_status_order").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--submissions", required=True)
    parser.add_argument("--universe", action="append", default=[], required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = build_discovered_employers(
        _read(Path(args.candidates)),
        _read(Path(args.submissions)),
        [_read(Path(path)) for path in args.universe],
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(f"A discovery shadow: {len(result)} unresolved/new employer observations")
    if len(result):
        print(result["discovery_status"].value_counts().to_string())


if __name__ == "__main__":
    main()
