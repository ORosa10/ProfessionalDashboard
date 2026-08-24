from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS_PATH = ROOT / "data" / "user_submitted_opportunities.csv"
RESEARCH_PATH = ROOT / "data" / "user_submitted_opportunity_research.csv"

RESEARCH_COLUMNS = [
    "submission_id", "title", "company", "canonical_company_id", "company_category",
    "location", "country", "topic", "role_summary_en", "company_profile", "role_profile",
    "salary_research", "salary_range", "targeting_scope", "review_status",
]

COMPANY_CATEGORIES = [
    "Big Four", "Consulting", "Corporate", "Banking & Financial Services",
    "Holding & Conglomerate", "Private Equity & Private Markets", "Investment Banking",
    "Public Markets & Asset Management", "Specialist & Boutique Funds", "Unclassified",
]

TOPICS = [
    "Transactions / M&A / Deals",
    "Corporate finance / valuation",
    "Restructuring / turnaround",
    "Treasury / financial risk / markets",
    "FP&A / controlling / performance management",
    "Finance-linked strategy and transformation",
    "Finance-linked data and analytics",
    "Private equity / investments",
    "Other / needs review",
]

API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.4-mini"


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "submitted-company"


def _company_lookup() -> dict[str, tuple[str, str, str]]:
    data_dir = ROOT / "data"
    frames: list[pd.DataFrame] = []
    base = data_dir / "company_universe.csv"
    if base.exists():
        frames.append(pd.read_csv(base).fillna(""))
    for path in sorted(data_dir.glob("company_universe_wave*.csv")):
        frames.append(pd.read_csv(path).fillna(""))
    if not frames:
        return {}
    universe = pd.concat(frames, ignore_index=True, sort=False).fillna("")

    category_frames: list[pd.DataFrame] = []
    for path in [data_dir / "company_categories.csv", data_dir / "company_category_overrides.csv"]:
        if path.exists():
            category_frames.append(pd.read_csv(path).fillna(""))
    if category_frames:
        cats = pd.concat(category_frames, ignore_index=True, sort=False)
        cats = cats.drop_duplicates("canonical_company_id", keep="last").set_index("canonical_company_id")
    else:
        cats = pd.DataFrame()

    lookup: dict[str, tuple[str, str, str]] = {}
    for _, row in universe.drop_duplicates("canonical_company_id", keep="last").iterrows():
        cid = str(row.get("canonical_company_id", "")).strip()
        company = str(row.get("company", "")).strip()
        if not cid or not company:
            continue
        category = str(row.get("company_category", "")).strip()
        if not cats.empty and cid in cats.index:
            category = str(cats.loc[cid].get("company_category", category)).strip()
        aliases = [company, *str(row.get("aliases_entities", "")).split(";")]
        for alias in aliases:
            key = _norm(alias)
            if key:
                lookup.setdefault(key, (cid, company, category or "Unclassified"))
    return lookup


def _schema() -> dict:
    string = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "title": string,
            "company": string,
            "company_category": {"type": "string", "enum": COMPANY_CATEGORIES},
            "location": string,
            "country": string,
            "topic": {"type": "string", "enum": TOPICS},
            "role_summary_en": string,
            "company_profile": string,
            "role_profile": string,
            "salary_research": string,
            "salary_range": string,
            "targeting_scope": string,
        },
        "required": [
            "title", "company", "company_category", "location", "country", "topic",
            "role_summary_en", "company_profile", "role_profile", "salary_research",
            "salary_range", "targeting_scope",
        ],
        "additionalProperties": False,
    }


def _extract_output_text(response_json: dict) -> str:
    chunks: list[str] = []
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()


def _source_urls(response_json: dict) -> list[str]:
    urls: list[str] = []
    for item in response_json.get("output", []):
        if item.get("type") != "web_search_call":
            continue
        action = item.get("action") or {}
        for source in action.get("sources", []) or []:
            url = str(source.get("url", "")).strip()
            if url and url not in urls:
                urls.append(url)
    return urls[:5]


def _research_one(row: pd.Series, api_key: str, model: str) -> dict[str, str]:
    title = str(row.get("title", "")).strip()
    company = str(row.get("company", "")).strip()
    location = str(row.get("location", "")).strip()
    description = str(row.get("role_summary_en", "")).strip()
    job_url = str(row.get("job_url", "")).strip()
    linkedin_url = str(row.get("linkedin_url", "")).strip()
    company_url = str(row.get("company_url", "")).strip()
    user_comment = str(row.get("user_comment", "")).strip()

    prompt = f"""
Research and enrich this manually submitted job opportunity for a finance professional.

Known data:
- Title: {title or 'unknown'}
- Company: {company or 'unknown'}
- Location: {location or 'unknown'}
- Job URL: {job_url or 'none'}
- Company job URL: {company_url or 'none'}
- LinkedIn URL: {linkedin_url or 'none'}
- Extracted job text: {description[:5000] or 'none'}
- User comment: {user_comment or 'none'}

Requirements:
1. Use web search for CURRENT role/company/location evidence. Prefer the live job posting, company career page, company sources, and role/company-specific salary sources. Use generic country benchmarks only as a secondary sanity check.
2. Identify the exact role, employer and location. Do not invent an employer if it is undisclosed.
3. Summarize the company and the real responsibilities/requirements of the role in concise English.
4. Salary research is MANDATORY. Give a realistic current market range for this exact role/company/location/seniority where evidence permits. If the posting states a legal/minimum salary, do not mistake it for the market range.
5. salary_research MUST begin with a clear personalized recommendation in this format: "SALARY EXPECTATION / WHAT TO ASK: ...". Assume a strong mid-level finance candidate with several years of relevant treasury/advisory/investment/banking experience. Include an opening ask, target expectation and sensible floor where possible, then explain the market evidence and uncertainty.
6. salary_range must be a short display string such as "EUR 80-95k base + bonus | Expectation: EUR 90k base". Never leave salary_range or salary_research blank. If evidence is weak, explicitly label the range as an estimate.
7. Company attractiveness and semantic role fit are separate. role_profile can explain responsibilities and notable fit/gaps, but do not assign an A/B/C company rating or a Strong/Moderate/Weak semantic label.
8. Use one of the allowed company categories and topics from the schema. targeting_scope should normally equal company_category.
""".strip()

    body = {
        "model": model,
        "store": False,
        "tools": [{"type": "web_search", "search_context_size": "medium"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "input": prompt,
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "manual_opportunity_enrichment",
                "strict": True,
                "schema": _schema(),
            },
        },
    }
    response = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=180,
    )
    response.raise_for_status()
    response_json = response.json()
    output_text = _extract_output_text(response_json)
    if not output_text:
        raise RuntimeError("OpenAI response contained no output text")
    result = json.loads(output_text)

    sources = _source_urls(response_json)
    salary_research = str(result.get("salary_research", "")).strip()
    if sources:
        salary_research += " SOURCES: " + " ; ".join(sources)
    result["salary_research"] = salary_research
    return {key: str(value or "").strip() for key, value in result.items()}


def enrich(submissions_path: Path, research_path: Path, max_items: int) -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for automatic opportunity enrichment")
    model = os.environ.get("OPPORTUNITY_ENRICHMENT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    submissions = pd.read_csv(submissions_path).fillna("")
    if research_path.exists() and research_path.stat().st_size > 0:
        research = pd.read_csv(research_path).fillna("")
    else:
        research = pd.DataFrame(columns=RESEARCH_COLUMNS)
    research = research.reindex(columns=RESEARCH_COLUMNS, fill_value="")
    completed = set(
        research.loc[
            research["review_status"].astype(str).str.contains("Enriched", case=False, na=False)
            & research["salary_range"].astype(str).str.strip().ne(""),
            "submission_id",
        ].astype(str)
    )

    pending = submissions[~submissions["submission_id"].astype(str).isin(completed)].copy()
    pending = pending.sort_values("submitted_at").head(max_items)
    if pending.empty:
        print("No submitted opportunities need enrichment")
        return 0

    company_lookup = _company_lookup()
    rows: list[dict[str, str]] = []
    for _, submission in pending.iterrows():
        sid = str(submission.get("submission_id", "")).strip()
        try:
            enriched = _research_one(submission, api_key, model)
        except Exception as exc:
            print(f"FAILED {sid}: {exc}")
            continue

        model_company = enriched.get("company", "")
        match = company_lookup.get(_norm(model_company))
        if match:
            canonical_id, canonical_company, category = match
        else:
            canonical_id = str(submission.get("canonical_company_id", "")).strip() or _slug(model_company)
            canonical_company = model_company or str(submission.get("company", "")).strip()
            category = enriched.get("company_category", "Unclassified") or "Unclassified"

        record = {col: "" for col in RESEARCH_COLUMNS}
        record.update({
            "submission_id": sid,
            "title": enriched.get("title", "") or str(submission.get("title", "")),
            "company": canonical_company,
            "canonical_company_id": canonical_id,
            "company_category": category,
            "location": enriched.get("location", "") or str(submission.get("location", "")),
            "country": enriched.get("country", ""),
            "topic": enriched.get("topic", "Other / needs review"),
            "role_summary_en": enriched.get("role_summary_en", ""),
            "company_profile": enriched.get("company_profile", ""),
            "role_profile": enriched.get("role_profile", ""),
            "salary_research": enriched.get("salary_research", ""),
            "salary_range": enriched.get("salary_range", ""),
            "targeting_scope": enriched.get("targeting_scope", "") or category,
            "review_status": "Auto-enriched - ready",
        })
        if not record["salary_range"] or not record["salary_research"]:
            print(f"FAILED {sid}: salary research missing from structured output")
            continue
        rows.append(record)
        print(f"ENRICHED {sid}: {record['company']} — {record['title']} — {record['salary_range']}")

    if not rows:
        return 0

    incoming = pd.DataFrame(rows).reindex(columns=RESEARCH_COLUMNS, fill_value="")
    existing = research[~research["submission_id"].astype(str).isin(incoming["submission_id"].astype(str))]
    combined = pd.concat([existing, incoming], ignore_index=True).reindex(columns=RESEARCH_COLUMNS, fill_value="")
    research_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(research_path, index=False)
    return len(incoming)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submissions", default=str(SUBMISSIONS_PATH))
    parser.add_argument("--research", default=str(RESEARCH_PATH))
    parser.add_argument("--max-items", type=int, default=10)
    args = parser.parse_args()
    count = enrich(Path(args.submissions), Path(args.research), args.max_items)
    print(f"Automatic B enrichment wrote {count} record(s)")


if __name__ == "__main__":
    main()
