"""Validate and report identity/detail quality across all persisted G lanes."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sourcing.g_data_quality import audit_g_frame, normalise_vacancy_url

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "g_quality_report.csv"


def load_g_frames() -> list[tuple[str, pd.DataFrame]]:
    frames = []
    for path in sorted(DATA.glob("jobs*.csv")):
        try:
            frame = pd.read_csv(path).fillna("")
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            continue
        if "job_id" in frame.columns:
            frames.append((path.name, frame))
    return frames


def build_report(frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    reports = []
    seen_urls: dict[str, tuple[str, str]] = {}
    for filename, frame in frames:
        report = audit_g_frame(frame)
        report.insert(0, "lane_file", filename)
        report["status"] = frame.reindex(report.index).get("status", "")
        for idx, row in frame.iterrows():
            url = normalise_vacancy_url(row.get("job_url", ""))
            if not url:
                continue
            previous = seen_urls.get(url)
            if previous and previous[0] != str(row.get("job_id", "")):
                report.loc[report.index == idx, "quality_flags"] = report.loc[report.index == idx, "quality_flags"].map(
                    lambda value: ";".join(filter(None, [value, "duplicate_vacancy_url"]))
                )
                report.loc[report.index == idx, "quality_status"] = "review"
            else:
                seen_urls[url] = (str(row.get("job_id", "")), filename)
        reports.append(report)
    if not reports:
        return pd.DataFrame(columns=["lane_file", "opportunity_id", "source_id", "quality_status", "quality_flags"])
    return pd.concat(reports, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    report = build_report(load_g_frames())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.out, index=False)
    flagged = int(report["quality_status"].eq("review").sum()) if not report.empty else 0
    # Historical/closed rows may legitimately have stale links. Only current
    # Open roles block the pipeline; all other issues remain visible in report.
    blocking = 0
    if report is not None and not report.empty:
        for idx, row in report.iterrows():
            has_identity_error = any(flag in row["quality_flags"] for flag in ("missing_or_invalid_title", "missing_job_url"))
            if has_identity_error and str(row.get("status", "Open")) == "Open":
                blocking += 1
    print(f"G quality: {len(report)} roles, {flagged} flagged, {blocking} blocking identity issues")
    if blocking:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
