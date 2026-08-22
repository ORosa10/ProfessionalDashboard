"""Registry-driven Workstream G board runner."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sourcing.big4_pilot import calibrate_jobs
from sourcing.board_academicwork import discover_academicwork
from sourcing.board_additional_adapters import discover_additional_board
from sourcing.board_catalog_adapters import discover_catalog_board
from sourcing.board_html_adapters import discover_html_jsonld_board
from sourcing.board_jobs_ch import discover_jobs_ch
from sourcing.board_jobly_fi import discover_jobly
from sourcing.board_jobbsafari_no import discover_jobbsafari_no
from sourcing.board_nav_no import discover_nav
from sourcing.board_official_adapters import discover_findajob, discover_mpsv
from sourcing.board_thehub import discover_thehub
from sourcing.board_sweep import (
    BOARDS_PATH, OUT_PATH, RUNS_PATH, STAGING_COLUMNS,
    _merge_with_existing, deduplicate_board_jobs, discover_arbeitsagentur,
    discover_platsbanken, translate_with_board_cache,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data" / "job_board_access_audit.csv"
COUNTRY_WEIGHTS_PATH = ROOT / "data" / "country_sourcing_weights.json"

# Search vocabulary is deliberately broader and more role-specific than the old
# generic nine-query set. G should build a deep candidate pool; C then makes the
# semantic judgement. These are discovery queries, never hard inclusion rules.
SEARCH_QUERIES = [
    # Treasury / markets
    "treasury",
    "corporate treasury",
    "treasury analyst",
    "treasury specialist",
    "treasury manager",
    "cash management",
    "liquidity management",
    "funding",
    "financial markets",
    "market risk",
    "liquidity risk",
    "interest rate risk",
    "FX risk",
    "hedging",
    "derivatives",
    "commodity risk",
    "ALM",
    # Investments / asset management
    "investment analyst",
    "investment associate",
    "investment manager",
    "private equity",
    "portfolio management",
    "portfolio analyst",
    "asset management",
    "equity analyst",
    "fixed income analyst",
    "credit analyst",
    "investment research",
    # Corporate finance / transactions
    "corporate finance",
    "corporate development",
    "M&A",
    "transaction services",
    "deal advisory",
    "valuation",
    "financial modelling",
    "capital advisory",
    "debt advisory",
    "restructuring",
    # Strategic finance / adjacent finance
    "strategic finance",
    "FP&A",
    "business controller",
    "finance business partner",
]

CATALOG_ADAPTERS = {
    "startupjobs_cz_html": "startupjobs-cz", "cocuma_cz_html": "cocuma-cz",
    "jobwinner_ch_html": "jobwinner-ch", "nzz_jobs_ch_html": "nzz-jobs-ch",
    "jobserve_uk_html": "jobserve-uk", "jobbland_se_html": "jobbland-se",
    "ledigajobb_se_html": "ledigajobb-se", "finansavisen_no_html": "finansavisen-no",
    "jobbank_dk_html": "jobbank-dk", "jobdanmark_dk_html": "jobdanmark-dk",
    "jobunivers_dk_html": "jobunivers-dk", "barona_fi_html": "barona-fi",
}


def _registry_with_audit() -> pd.DataFrame:
    boards = pd.read_csv(BOARDS_PATH).fillna("")
    if not AUDIT_PATH.exists():
        return boards
    audit = pd.read_csv(AUDIT_PATH).fillna("")
    if audit.empty or "board_id" not in audit.columns:
        return boards
    audit = audit.drop_duplicates("board_id", keep="last").set_index("board_id")
    for target, source in (("status", "status_override"), ("adapter", "adapter_override"), ("enabled", "enabled_override")):
        if source in audit.columns:
            mapped = boards["board_id"].map(audit[source]).fillna("")
            boards[target] = mapped.where(mapped.ne(""), boards[target])
    return boards


def _country_weights() -> dict[str, float]:
    if not COUNTRY_WEIGHTS_PATH.exists():
        return {}
    try:
        payload = json.loads(COUNTRY_WEIGHTS_PATH.read_text(encoding="utf-8"))
        weights = {str(k): float(v) for k, v in payload.get("weights", {}).items() if float(v) > 0}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {country: weight / total for country, weight in weights.items()}


def _country_board_budgets(runnable: pd.DataFrame, base_per_query: int, base_max_details: int) -> dict[str, tuple[int, int]]:
    """Allocate G effort by country target while neutralising number of active boards.

    A country with more runnable sources should not automatically get more sourcing
    effort. Each board receives a share of the country's total target budget.
    """
    weights = _country_weights()
    if runnable.empty or not weights:
        return {str(row.board_id): (base_per_query, base_max_details) for row in runnable.itertuples(index=False)}

    counts = Counter(str(country) for country in runnable["country"])
    n_boards = max(len(runnable), 1)
    budgets: dict[str, tuple[int, int]] = {}
    for row in runnable.itertuples(index=False):
        country = str(row.country)
        country_weight = weights.get(country)
        if not country_weight or counts[country] <= 0:
            scale = 1.0
        else:
            scale = (country_weight / counts[country]) * n_boards
        scale = min(2.5, max(0.35, scale))
        per_query = max(2, round(base_per_query * scale))
        max_details = max(12, round(base_max_details * scale))
        budgets[str(row.board_id)] = (per_query, max_details)
    return budgets


def _run_board(row: object, per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    adapter = str(getattr(row, "adapter", ""))
    if adapter == "jobtech_api": return discover_platsbanken(SEARCH_QUERIES, per_query)
    if adapter == "arbeitsagentur_html": return discover_arbeitsagentur(SEARCH_QUERIES, per_query, max_details)
    if adapter == "mpsv_open_data": return discover_mpsv(max_details)
    if adapter == "findajob_uk_html": return discover_findajob(SEARCH_QUERIES, per_query, max_details)
    if adapter == "nav_stilling_feed": return discover_nav(max_details)
    if adapter == "jobbsafari_no_html": return discover_jobbsafari_no(SEARCH_QUERIES, per_query, max_details)
    if adapter == "academicwork_dk_html": return discover_academicwork("academicwork-dk", max_details)
    if adapter == "academicwork_fi_html": return discover_academicwork("academicwork-fi", max_details)
    if adapter in CATALOG_ADAPTERS: return discover_catalog_board(CATALOG_ADAPTERS[adapter], SEARCH_QUERIES, per_query, max_details)
    html_map = {
        "jobs_cz_html": ("jobs-cz", "Czechia"), "prace_cz_html": ("prace-cz", "Czechia"),
        "stepstone_de_html": ("stepstone-de", "Germany"), "stellenanzeigen_de_html": ("stellenanzeigen-de", "Germany"),
        "stepstone_at_html": ("stepstone-at", "Austria"), "karriere_at_html": ("karriere-at", "Austria"),
        "willhaben_at_html": ("willhaben-at", "Austria"), "jobbsafari_se_html": ("jobbsafari-se", "Sweden"),
    }
    if adapter in html_map:
        source_id, market = html_map[adapter]
        return discover_html_jsonld_board(source_id, market, SEARCH_QUERIES, per_query, max_details)
    if adapter == "jobs_ch_html": return discover_jobs_ch(SEARCH_QUERIES, per_query, max_details)
    if adapter == "jobup_ch_html": return discover_additional_board("jobup-ch", "Switzerland", SEARCH_QUERIES, per_query, max_details)
    if adapter == "cv_library_uk_html": return discover_additional_board("cv-library-uk", "United Kingdom", SEARCH_QUERIES, per_query, max_details)
    if adapter == "jobly_fi_html": return discover_jobly(per_query, max_details)
    if adapter == "thehub_html": return discover_thehub(max_details)
    return [], [f"Unsupported adapter: {adapter}"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--runs", default=str(RUNS_PATH))
    parser.add_argument("--per-query", type=int, default=8)
    parser.add_argument("--max-details", type=int, default=65)
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--source-id", action="append", default=[])
    args = parser.parse_args()

    boards = _registry_with_audit()
    runnable = boards[
        boards["enabled"].astype(str).str.lower().eq("true")
        & boards["status"].isin(["active", "adapter_ready"])
    ]
    if args.source_id:
        runnable = runnable[runnable["board_id"].isin(args.source_id)]

    budgets = _country_board_budgets(runnable, args.per_query, args.max_details)
    records: list[dict] = []
    run_rows: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()
    for row in runnable.itertuples(index=False):
        board_per_query, board_max_details = budgets.get(str(row.board_id), (args.per_query, args.max_details))
        try:
            found, errors = _run_board(row, board_per_query, board_max_details)
        except Exception as exc:
            found, errors = [], [f"runner: {type(exc).__name__}: {exc}"]
        records.extend(found)
        run_rows.append({
            "run_at": started,
            "board_id": row.board_id,
            "country": row.country,
            "adapter": row.adapter,
            "registry_status": row.status,
            "queries": len(SEARCH_QUERIES),
            "per_query_budget": board_per_query,
            "max_details_budget": board_max_details,
            "verified_jobs": len(found),
            "errors": " | ".join(errors[:12]),
        })
        print(
            f"{row.board_id} [{row.status}] budget={board_per_query}/{board_max_details}: "
            f"verified={len(found)} errors={len(errors)}"
        )

    out = pd.DataFrame(records).reindex(columns=STAGING_COLUMNS, fill_value="")
    if not out.empty:
        out = calibrate_jobs(deduplicate_board_jobs(out.drop_duplicates("job_id", keep="first")))
        if not args.no_translate:
            cache_path = Path(args.out)
            out = translate_with_board_cache(
                out,
                cache_path if cache_path.exists() and cache_path.stat().st_size > 0 else Path("__missing_board_cache__.csv"),
            )
    out_path = Path(args.out)
    if out.empty:
        if out_path.exists() and out_path.stat().st_size > 0:
            try:
                out = pd.read_csv(out_path).fillna("").reindex(columns=STAGING_COLUMNS, fill_value="")
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
                out = pd.DataFrame(columns=STAGING_COLUMNS)
        else:
            out = pd.DataFrame(columns=STAGING_COLUMNS)
    elif out_path.exists() and out_path.stat().st_size > 0:
        out = _merge_with_existing(out, out_path).reindex(columns=STAGING_COLUMNS, fill_value="")
    if not out.empty:
        out = out.sort_values(["status", "calibration_score", "last_seen_at"], ascending=[True, False, False])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    runs_path = Path(args.runs)
    runs = pd.DataFrame(run_rows)
    if runs_path.exists() and runs_path.stat().st_size > 0:
        try:
            runs = pd.concat([pd.read_csv(runs_path).fillna(""), runs], ignore_index=True, sort=False).tail(500)
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            pass
    runs.to_csv(runs_path, index=False)
    print(f"wrote {len(out)} board-sourced roles to {out_path}")


if __name__ == "__main__":
    main()
