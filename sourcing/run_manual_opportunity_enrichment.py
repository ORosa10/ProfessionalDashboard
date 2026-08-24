from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sourcing.enrich_user_submitted_opportunities import (
    RESEARCH_COLUMNS,
    RESEARCH_PATH,
    SUBMISSIONS_PATH,
    enrich,
)

ENRICHMENT_COLUMNS = [
    "title", "company", "canonical_company_id", "company_category", "location", "country",
    "topic", "role_summary_en", "company_profile", "role_profile", "salary_research",
    "salary_range", "targeting_scope", "review_status",
]


def sync_research_to_submissions(submissions_path: Path, research_path: Path) -> int:
    submissions = pd.read_csv(submissions_path).fillna("")
    if submissions.empty or not research_path.exists():
        return 0
    research = pd.read_csv(research_path).fillna("")
    if research.empty:
        return 0
    research = research.reindex(columns=RESEARCH_COLUMNS, fill_value="")
    latest = research.drop_duplicates("submission_id", keep="last").set_index("submission_id")

    changed = 0
    for idx, row in submissions.iterrows():
        sid = str(row.get("submission_id", ""))
        if sid not in latest.index:
            continue
        enriched = latest.loc[sid]
        before = tuple(str(row.get(col, "")) for col in ENRICHMENT_COLUMNS)
        for col in ENRICHMENT_COLUMNS:
            value = str(enriched.get(col, "")).strip()
            if value:
                submissions.at[idx, col] = value
        # B is an intentional manual intake lane. Adding a role is the positive preference signal.
        if str(submissions.at[idx, "feedback"]).strip() in {"", "Unrated"}:
            submissions.at[idx, "feedback"] = "Interested"
        submissions.at[idx, "calibration_signal"] = "User-supplied positive example"
        after = tuple(str(submissions.at[idx, col]) for col in ENRICHMENT_COLUMNS)
        if after != before:
            changed += 1

    if changed:
        submissions.to_csv(submissions_path, index=False)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submissions", default=str(SUBMISSIONS_PATH))
    parser.add_argument("--research", default=str(RESEARCH_PATH))
    parser.add_argument("--max-items", type=int, default=10)
    args = parser.parse_args()
    submissions_path = Path(args.submissions)
    research_path = Path(args.research)
    enriched = enrich(submissions_path, research_path, args.max_items)
    synced = sync_research_to_submissions(submissions_path, research_path)
    print(f"B enrichment: {enriched} researched, {synced} intake rows synchronized")


if __name__ == "__main__":
    main()
