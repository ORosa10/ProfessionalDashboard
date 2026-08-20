"""Workstream G runner with registry-driven board adapters.

`active` sources are production adapters. `adapter_ready` sources are included
in the run so new adapters can be validated in GitHub Actions before they are
promoted to active. Retrieval failures are recorded per source and never stop
other boards from running.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sourcing.big4_pilot import calibrate_jobs
from sourcing.board_html_adapters import discover_html_jsonld_board
from sourcing.board_sweep import (
    BOARDS_PATH,
    DEFAULT_QUERIES,
    OUT_PATH,
    RUNS_PATH,
    STAGING_COLUMNS,
    _merge_with_existing,
    deduplicate_board_jobs,
    discover_arbeitsagentur,
    discover_platsbanken,
    translate_with_board_cache,
)


def _run_board(row: object, per_query: int, max_details: int) -> tuple[list[dict], list[str]]:
    adapter = str(getattr(row, "adapter", ""))
    if adapter == "jobtech_api":
        return discover_platsbanken(DEFAULT_QUERIES, per_query)
    if adapter == "arbeitsagentur_html":
        return discover_arbeitsagentur(DEFAULT_QUERIES, per_query, max_details)
    if adapter == "jobs_cz_html":
        return discover_html_jsonld_board(
            "jobs-cz", "Czechia", DEFAULT_QUERIES, per_query, max_details
        )
    if adapter == "prace_cz_html":
        return discover_html_jsonld_board(
            "prace-cz", "Czechia", DEFAULT_QUERIES, per_query, max_details
        )
    if adapter == "stepstone_at_html":
        return discover_html_jsonld_board(
            "stepstone-at", "Austria", DEFAULT_QUERIES, per_query, max_details
        )
    if adapter == "karriere_at_html":
        return discover_html_jsonld_board(
            "karriere-at", "Austria", DEFAULT_QUERIES, per_query, max_details
        )
    if adapter == "jobbsafari_se_html":
        return discover_html_jsonld_board(
            "jobbsafari-se", "Sweden", DEFAULT_QUERIES, per_query, max_details
        )
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

    boards = pd.read_csv(BOARDS_PATH).fillna("")
    runnable = boards[
        boards["enabled"].astype(str).str.lower().eq("true")
        & boards["status"].isin(["active", "adapter_ready"])
    ]
    if args.source_id:
        runnable = runnable[runnable["board_id"].isin(args.source_id)]

    records: list[dict] = []
    run_rows: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()
    for row in runnable.itertuples(index=False):
        try:
            found, errors = _run_board(row, args.per_query, args.max_details)
        except Exception as exc:
            found, errors = [], [f"runner: {type(exc).__name__}: {exc}"]
        records.extend(found)
        run_rows.append({
            "run_at": started,
            "board_id": row.board_id,
            "country": row.country,
            "adapter": row.adapter,
            "registry_status": row.status,
            "queries": len(DEFAULT_QUERIES),
            "verified_jobs": len(found),
            "errors": " | ".join(errors[:12]),
        })
        print(
            f"{row.board_id} [{row.status}]: verified={len(found)} "
            f"errors={len(errors)}"
        )

    out = pd.DataFrame(records).reindex(columns=STAGING_COLUMNS, fill_value="")
    if not out.empty:
        out = deduplicate_board_jobs(out.drop_duplicates("job_id", keep="first"))
        out = calibrate_jobs(out)
        if not args.no_translate:
            out = translate_with_board_cache(out, Path(args.out))

    out_path = Path(args.out)
    out = _merge_with_existing(out, out_path).reindex(columns=STAGING_COLUMNS, fill_value="")
    if not out.empty:
        out = out.sort_values(
            ["status", "calibration_score", "last_seen_at"],
            ascending=[True, False, False],
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    runs_path = Path(args.runs)
    runs = pd.DataFrame(run_rows)
    if runs_path.exists():
        prior = pd.read_csv(runs_path).fillna("")
        runs = pd.concat([prior, runs], ignore_index=True, sort=False).tail(500)
    runs.to_csv(runs_path, index=False)
    print(f"wrote {len(out)} board-sourced roles to {out_path}")


if __name__ == "__main__":
    main()
