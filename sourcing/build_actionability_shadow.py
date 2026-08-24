"""Deterministic shadow actionability evaluator for the future C -> J gate.

This is intentionally separate from semantic fit. A C=Strong role can be marked
non-actionable here without changing its C rating. The evaluator uses only
explicit evidence and the shadow policy file; unknown legal/work-authorization
facts are warnings, never inferred hard blockers.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from sourcing.filter_language_requirements import blocking_language_requirement


OUTPUT_COLUMNS = [
    "opportunity_id", "candidate_id", "company", "title", "semantic_fit",
    "country_bucket", "source_status", "job_url", "actionable", "blockers",
    "warnings", "language_blocker", "link_status", "evaluated_at",
]

TARGET_CODE_MAP = {
    "CZ": "Czechia",
    "DE": "Germany",
    "AT": "Austria",
    "CH": "Switzerland",
    "GB": "United Kingdom",
    "UK": "United Kingdom",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "FI": "Finland",
}

COMMON_OUTSIDE_CODES = {
    "US", "CA", "PL", "FR", "IT", "ES", "NL", "BE", "IE", "PT", "LU",
    "HU", "RO", "BG", "GR", "TR", "AU", "NZ", "SG", "HK", "AE", "IN",
}

WORK_AUTH_PATTERNS = [
    r"must (?:already )?have (?:the )?right to work",
    r"must be (?:legally )?authorized to work",
    r"must have (?:existing )?work authori[sz]ation",
    r"no (?:visa )?sponsorship",
    r"cannot (?:provide|offer) (?:visa )?sponsorship",
    r"not able to sponsor",
]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _read_policy(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _text(row: pd.Series) -> str:
    return " ".join(
        str(row.get(col, "") or "")
        for col in ["title", "description_en", "description", "calibration_note"]
    )


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _structured_country_codes(raw: str) -> set[str]:
    """Read ISO-like codes only from delimiter-separated location positions.

    Examples that should match: `Europe, PL`, `North America, US`, `DE`.
    Ordinary prose such as `remote in Europe` must NOT turn the word `in` into
    the India country code.
    """
    upper = str(raw or "").upper().strip()
    codes = set(re.findall(r"(?:^|[,·/|]\s*)([A-Z]{2})(?=$|[\s,·/|])", upper))
    if re.fullmatch(r"[A-Z]{2}", upper):
        codes.add(upper)
    return codes


def _explicit_outside_geography(row: pd.Series, target_geographies: set[str]) -> tuple[bool, str]:
    country = str(row.get("country_bucket", "") or "").strip()
    if country in target_geographies:
        return False, "target"
    if country and country not in {"Other / Unresolved", "Multi-region", "Remote", "Unknown"}:
        return True, country

    raw = f"{row.get('market', '')} {row.get('location', '')}".strip()
    tokens = _structured_country_codes(raw)
    target_codes = set(TARGET_CODE_MAP)
    outside_codes = tokens & COMMON_OUTSIDE_CODES
    if outside_codes and not (tokens & target_codes):
        return True, sorted(outside_codes)[0]

    lower = raw.lower()
    explicit_names = {
        "united states": "United States",
        "usa": "United States",
        "canada": "Canada",
        "poland": "Poland",
        "france": "France",
        "italy": "Italy",
        "spain": "Spain",
        "netherlands": "Netherlands",
        "belgium": "Belgium",
        "ireland": "Ireland",
    }
    for needle, label in explicit_names.items():
        if needle in lower:
            return True, label
    return False, "unresolved"


def _age_days(value: object, as_of: pd.Timestamp) -> int | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return max(0, int((as_of - parsed).total_seconds() // 86400))


def _as_utc_timestamp(value: str | None) -> pd.Timestamp:
    parsed = pd.Timestamp(value or date.today().isoformat())
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def evaluate_actionability(
    candidates: pd.DataFrame,
    semantic: pd.DataFrame,
    policy: dict,
    *,
    as_of: str | None = None,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frame = candidates.fillna("").copy()
    for col in [
        "candidate_id", "job_id", "company", "title", "country_bucket", "market",
        "location", "status", "job_url", "description", "description_en",
        "calibration_note", "date_posted", "last_seen_at", "link_health",
    ]:
        if col not in frame.columns:
            frame[col] = ""
    frame["opportunity_id"] = frame.apply(
        lambda row: str(row.get("job_id", "")).strip() or str(row.get("candidate_id", "")).strip(),
        axis=1,
    )

    sem_map: dict[str, str] = {}
    if not semantic.empty and {"opportunity_id", "fit"}.issubset(semantic.columns):
        sem = semantic.fillna("").drop_duplicates("opportunity_id", keep="last")
        sem_map = dict(zip(sem["opportunity_id"].astype(str), sem["fit"].astype(str)))

    target_geographies = set(policy.get("target_geographies", []))
    hard_statuses = {str(x).lower() for x in policy.get("hard_blockers", {}).get("explicit_vacancy_status", [])}
    dead_links = {str(x).lower() for x in policy.get("hard_blockers", {}).get("confirmed_dead_link", [])}
    old_days = int(policy.get("warnings_not_blockers", {}).get("old_posting_days", 45))
    stale_days = int(policy.get("warnings_not_blockers", {}).get("stale_last_seen_days", 7))
    eval_ts = _as_utc_timestamp(as_of)

    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        blockers: list[str] = []
        warnings: list[str] = []

        status = str(row.get("status", "") or "").strip()
        status_lower = status.lower()
        if status_lower in hard_statuses:
            _append_unique(blockers, f"vacancy_status:{status}")

        language_reason = blocking_language_requirement(_text(row))
        if language_reason:
            _append_unique(blockers, f"language:{language_reason}")
        elif status_lower == "pass_language":
            # Compatibility fallback while the current live G mutates board status.
            _append_unique(blockers, "language:legacy_pass_language_status")

        outside, geo_detail = _explicit_outside_geography(row, target_geographies)
        if outside:
            _append_unique(blockers, f"geography:{geo_detail}")
        elif geo_detail == "unresolved":
            _append_unique(warnings, "geography:needs_resolution")

        job_url = str(row.get("job_url", "") or "").strip()
        if not job_url:
            _append_unique(blockers, "link:missing_job_url")

        link_status = str(row.get("link_health", "") or "").strip().lower()
        if link_status in dead_links:
            _append_unique(blockers, f"link:{link_status}")
        elif not link_status:
            _append_unique(warnings, "link:not_revalidated")

        text = _text(row).lower()
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in WORK_AUTH_PATTERNS):
            _append_unique(warnings, "work_authorization:manual_check")

        posted_age = _age_days(row.get("date_posted", ""), eval_ts)
        if posted_age is not None and posted_age > old_days:
            _append_unique(warnings, f"freshness:posting_{posted_age}d_old")
        seen_age = _age_days(row.get("last_seen_at", ""), eval_ts)
        if seen_age is not None and seen_age > stale_days:
            _append_unique(warnings, f"freshness:last_seen_{seen_age}d_ago")

        oid = str(row.get("opportunity_id", ""))
        rows.append({
            "opportunity_id": oid,
            "candidate_id": str(row.get("candidate_id", "")),
            "company": str(row.get("company", "")),
            "title": str(row.get("title", "")),
            "semantic_fit": sem_map.get(oid, ""),
            "country_bucket": str(row.get("country_bucket", "")),
            "source_status": status,
            "job_url": job_url,
            "actionable": len(blockers) == 0,
            "blockers": "; ".join(blockers),
            "warnings": "; ".join(warnings),
            "language_blocker": language_reason,
            "link_status": link_status or "not_checked",
            "evaluated_at": eval_ts.date().isoformat(),
        })

    return pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS, fill_value="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate pre-J actionability in shadow mode")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--as-of")
    args = parser.parse_args()

    result = evaluate_actionability(
        _read_csv(Path(args.candidates)),
        _read_csv(Path(args.semantic)),
        _read_policy(Path(args.policy)),
        as_of=args.as_of,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    actionable = int(result["actionable"].astype(bool).sum()) if not result.empty else 0
    print(f"shadow actionability: {actionable}/{len(result)} candidates actionable")


if __name__ == "__main__":
    main()
