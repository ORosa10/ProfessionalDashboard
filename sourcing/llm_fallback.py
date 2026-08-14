"""LLM-assisted fallback for career pages that don't match any known ATS
adapter (JS-rendered custom sites, unsupported platforms, etc).

Renders the page with a headless Chromium (Playwright) so JS-only career
widgets show real content -- this only works in GitHub Actions, which has
full network access and can install browser binaries; the interactive
sandbox used to build this pipeline blocks outbound network entirely, so
this module cannot be exercised there. Extraction of job postings from the
rendered, arbitrarily-structured page is done by Gemini 2.5 Flash on its
free tier. This deliberately keeps LLM usage off the user's Claude/Cowork
subscription and off any paid API (explicit cost decision -- see
claude/build-log.md) by using a different, no-cost provider instead.

Requires a GEMINI_API_KEY repository secret. If it's missing, every source
routed to this adapter is skipped with a clear error in source_runs rather
than failing the whole workflow.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import requests

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

EXTRACTION_PROMPT = """You are looking at the rendered text content of a company's careers/jobs page.
Extract every individual job opening that is plausibly relevant to finance, investment, treasury,
risk, accounting, strategy, corporate development, or related business/analytical roles.
Ignore navigation text, cookie banners, and clearly unrelated postings (pure IT/engineering, sales,
retail, manual labor, internal HR/talent-acquisition roles).

Return ONLY a JSON array (no markdown fencing, no commentary). Each item:
{{"title": "...", "location": "...", "url": "..."}}

If no per-job URL is visible in the text, reuse the page URL below for every item.
If there are no relevant postings, return [].

PAGE URL: {page_url}

PAGE TEXT:
{page_text}
"""

JOB_LINK_PATTERN = re.compile(r"job|career|vacan|position|opening|stellenangebot", re.I)


def _render_page(url: str, timeout_ms: int = 25000) -> tuple[str, list[str]]:
    """Render `url` with headless Chromium; return (visible_text, discovered_links)."""
    from playwright.sync_api import sync_playwright  # imported lazily -- only needed here

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        except Exception:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        text = page.inner_text("body")
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        browser.close()
    return text[:15000], links


def _call_gemini(page_url: str, page_text: str) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = EXTRACTION_PROMPT.format(page_url=page_url, page_text=page_text)
    try:
        response = requests.post(
            f"{GEMINI_URL}?key={api_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
            timeout=60,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        # requests' exception message embeds the full request URL --
        # including "?key=<GEMINI_API_KEY>". That string was ending up in
        # source_runs_*.csv's errors column and getting committed, which
        # GitHub's push protection correctly blocked (GH013: GCP API Key
        # Bound to a Service Account) on 2026-08-14. Never let the raw key
        # reach a log line, CSV cell, or commit again.
        raise RuntimeError(
            f"Gemini request failed: {type(exc).__name__}: "
            f"{str(exc).replace(api_key, '***')}"
        ) from None
    payload = response.json()
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        items = json.loads(match.group(0)) if match else []
    return items if isinstance(items, list) else []


def discover_jobs_llm(source, max_pages: int = 2) -> tuple[list[dict], dict]:
    """discover_source-compatible entry point: (jobs, run_info)."""
    from sourcing import big4_pilot as common  # local import avoids a module cycle

    started = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    jobs: dict[str, dict] = {}
    pages_checked = 0

    try:
        text, links = _render_page(source.seed_url)
        pages_checked = 1
        items = _call_gemini(source.seed_url, text)
        if not items and max_pages > 1:
            job_link = next(
                (link for link in links if JOB_LINK_PATTERN.search(link) and link != source.seed_url),
                None,
            )
            if job_link:
                text2, _ = _render_page(job_link)
                items = _call_gemini(job_link, text2)
                pages_checked = 2
        for item in items:
            title = common.normalize(str(item.get("title", "")))
            if not title or not common.is_relevant_listing_title(title):
                continue
            job_url = str(item.get("url") or source.seed_url)
            job_id = common.stable_job_id(source, job_url or title)
            jobs[job_id] = {
                "job_id": job_id,
                "canonical_company_id": source.canonical_company_id,
                "company": source.company,
                "title": title,
                "description": "",
                "market": source.market,
                "location": common.normalize(str(item.get("location", ""))),
                "priority_locations": source.get("priority_locations", ""),
                "job_url": job_url,
                "source_url": source.seed_url,
                "source_id": source.source_id,
                "date_posted": "",
                "discovered_at": started,
                "last_seen_at": started,
                "verification": "LLM-assisted extraction (Gemini 2.5 Flash, headless render)",
                "status": "Open",
            }
    except Exception as exc:
        errors.append(f"{source.seed_url}: {type(exc).__name__}: {exc}")

    run = {
        "run_at": started,
        "source_id": source.source_id,
        "company": source.company,
        "market": source.market,
        "seed_url": source.seed_url,
        "pages_checked": pages_checked,
        "candidate_job_pages": pages_checked,
        "verified_jobs": len(jobs),
        "errors": " | ".join(errors[:5]),
    }
    return list(jobs.values()), run
