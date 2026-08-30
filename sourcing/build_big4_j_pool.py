from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BIG4 = {"deloitte", "ey", "kpmg", "pwc"}
POSITIVE = (
    "treasury", "financial risk", "market risk", "risk management", "valuation",
    "corporate finance", "m&a", "merger", "acquisition", "transaction services",
    "due diligence", "deal advisory", "deals", "restructuring", "turnaround",
    "strategy and transactions", "finance transformation", "cfo advisory",
    "capital markets", "investment banking", "financial modelling", "financial modeling",
    "business modelling", "business modeling", "portfolio", "derivative", "hedging",
    "liquidity", "cash management", "working capital", "project finance",
)
EXCLUDE = (
    "audit", "assurance", "tax", "steuer", "accounting", "buchhaltung", "payroll",
    "sap", "erp", "cyber", "software", "developer", "data engineer", "legal",
    "procurement", "human resources", "recruit", "internal it", "controller",
    "actuarial", "compliance", "regulatory", "insurance", "technology", "engineering",
    "supply chain", "human capital", "artificial intelligence", "data & ai",
)


def _text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _relevant(row: pd.Series) -> tuple[bool, str]:
    title = _text(row.get("title"))
    body = _text(row.get("description_en")) or _text(row.get("description"))
    hay = f"{title} {body}".lower()
    title_low = title.lower()
    # Tax, audit, generic controlling, actuarial, compliance and IT tracks are
    # not part of this dedicated target lane even when the title also says M&A
    # or risk. They would otherwise dominate Big Four career pages through
    # incidental keyword matches.
    if any(term in title_low for term in EXCLUDE):
        return False, "Excluded generic/non-target title"
    hits = [term for term in POSITIVE if term in title_low]
    body_hits = [term for term in POSITIVE if term in body.lower() and term not in hits]
    # A clearly relevant title wins even if the generic description contains
    # accounting or audit boilerplate. Otherwise avoid generic Big Four finance
    # administration, audit, tax and technology roles.
    if hits:
        return True, "Title: " + ", ".join(hits)
    if not body_hits:
        return False, ""
    if sum(term in hay for term in EXCLUDE) >= 3 and not any(
        term in title_low for term in ("finance transformation", "deal", "transaction", "valuation", "treasury")
    ):
        return False, "Excluded generic/non-target workstream"
    return True, "Description: " + ", ".join(body_hits[:6])


def build(inputs: list[Path], output: Path) -> int:
    frames: list[pd.DataFrame] = []
    for path in inputs:
        if not path.exists() or not path.stat().st_size:
            continue
        frame = pd.read_csv(path).fillna("")
        if "canonical_company_id" not in frame.columns:
            continue
        frame = frame[frame["canonical_company_id"].astype(str).str.lower().isin(BIG4)].copy()
        if not frame.empty:
            frames.append(frame)
    if not frames:
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output, index=False)
        return 0

    jobs = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    jobs = jobs.drop_duplicates("job_id", keep="last")
    decisions = jobs.apply(_relevant, axis=1, result_type="expand")
    jobs = jobs[decisions[0]].copy()
    jobs["big4_relevance_reason"] = decisions.loc[jobs.index, 1]
    jobs["big4_stream"] = "J Big 4"
    jobs["source_stream"] = "Big Four"
    jobs["status"] = jobs.get("status", "Open").replace("", "Open")
    jobs = jobs.sort_values(["canonical_company_id", "market", "title"], kind="stable")
    output.parent.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(output, index=False)
    return len(jobs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", dest="inputs", default=[])
    parser.add_argument("--output", default="data/j_big4_pool.csv")
    args = parser.parse_args()
    inputs = [ROOT / item for item in args.inputs] or [ROOT / "data/jobs.csv"]
    print(f"Built J Big 4 pool with {build(inputs, ROOT / args.output)} relevant roles")


if __name__ == "__main__":
    main()

