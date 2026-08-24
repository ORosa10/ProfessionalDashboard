from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from sourcing.salary_research_free import (
    REQUEST_COLUMNS,
    RESEARCH_COLUMNS,
    REQUESTS_PATH,
    RESEARCH_PATH,
    SUBMISSIONS_PATH,
    _load_csv,
    _text,
    research_salary,
)


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
    research_map = research.drop_duplicates("submission_id", keep="last").set_index("submission_id")

    processed = 0
    now = datetime.now(timezone.utc).isoformat()
    data_cols = [c for c in RESEARCH_COLUMNS if c != "submission_id"]

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
            record = {col: "" for col in data_cols}

        # Never overwrite a curated / ChatGPT-researched salary with the lower-fidelity
        # deterministic free-web estimate. Zero-cost estimates can refresh themselves.
        existing_salary_research = _text(record.get("salary_research"))
        curated_salary = bool(existing_salary_research) and not existing_salary_research.startswith("ZERO-COST WEB RESEARCH")
        if curated_salary:
            requests.loc[req_idx, ["status", "completed_at", "message"]] = [
                "done", now, "Existing curated salary research kept; zero-cost refresh not applied."
            ]
            print(f"KEPT CURATED {sid}")
            processed += 1
            continue

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

        research_map.loc[sid, data_cols] = [record.get(c, "") for c in data_cols]
        requests.loc[req_idx, ["status", "completed_at", "message"]] = [status, now, salary_range]
        processed += 1
        print(f"SALARY {sid}: {salary_range} ({status})")

    research_map.reset_index().reindex(columns=RESEARCH_COLUMNS, fill_value="").to_csv(RESEARCH_PATH, index=False)
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
