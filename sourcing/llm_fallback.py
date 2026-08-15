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
import time
from datetime import datetime, timezone

import requests

# Free-tier Gemini rate limit -- run #10 (2026-08-15 05:xx) 404-free but every
# single call came back "429 Too Many Requests" because sector_pilot.py's
# generic 0.15s inter-source pause is nowhere near enough headroom for a
# free-tier RPM cap. Space calls out and retry-with-backoff on a 429 instead
# of just recording the failure and moving on.
_MIN_SECONDS_BETWEEN_CALLS = 4.0
_last_call_at = 0.0

GEMINI_MODEL = "gemini-3.6-flash"
# Google migrated the free-tier REST surface from the old
# v1beta/models/{model}:generateContent endpoint to the Interactions API
# sometime after this codebase's original 2025 knowledge cutoff. Confirmed
# against ai.google.dev/gemini-api/docs/quickstart on 2026-08-14 (the
# endpoint, header, and body shape below are quoted verbatim from that
# page's own curl example -- fetched twice independently, identical both
# times). The endpoint itself is real (GET on /v1beta/models/* returns 403
# "needs auth", not 404 "no such path"), but the run-#9 attempt still 404'd
# because it kept the old "gemini-2.5-flash" model id -- the quickstart's
# own example model, gemini-3.6-flash, is what's actually wired up under
# Interactions today. Key goes in a header now, never in the URL/query
# string, so it can't leak into an exception message either.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
JOB_ITEMS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "location": {"type": "string"},
            "url": {"type": "string"},
        },
        "required": ["title"],
    },
}

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


def _extract_interaction_text(payload: dict) -> str:
    """Pull the model's text out of an Interactions API response, tolerating
    either the documented `output_text` convenience field or having to walk
    `steps[].content[]` ourselves if that field isn't present.
    """
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    chunks: list[str] = []
    for step in payload.get("steps", []) or []:
        for block in step.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                chunks.append(str(block.get("text", "")))
    return "".join(chunks)


def _call_gemini(page_url: str, page_text: str, max_retries: int = 3) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = EXTRACTION_PROMPT.format(page_url=page_url, page_text=page_text)

    global _last_call_at
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        wait = _MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.post(
                GEMINI_URL,
                headers={
                    # Interactions API takes the key as a header, not a URL
                    # query param -- so it can never end up embedded in a
                    # request-URL string inside an exception message, log
                    # line, or CSV cell.
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": GEMINI_MODEL,
                    "input": prompt,
                    "response_format": {
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": JOB_ITEMS_SCHEMA,
                    },
                },
                timeout=60,
            )
            _last_call_at = time.monotonic()
            if response.status_code == 429 and attempt < max_retries - 1:
                # Exponential backoff (4s, 8s, 16s...) rather than failing
                # the source outright on the first free-tier rate-limit hit
                # -- run #10 (2026-08-15) 429'd on every single llm-adapter
                # source because there was no backoff at all.
                time.sleep(_MIN_SECONDS_BETWEEN_CALLS * (2 ** attempt))
                continue
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as exc:
            _last_call_at = time.monotonic()
            last_exc = exc
            if isinstance(exc, requests.exceptions.HTTPError) and (
                exc.response is not None and exc.response.status_code == 429
            ) and attempt < max_retries - 1:
                time.sleep(_MIN_SECONDS_BETWEEN_CALLS * (2 ** attempt))
                continue
            raise RuntimeError(f"Gemini request failed: {type(exc).__name__}: {exc}") from None
    else:
        raise RuntimeError(
            f"Gemini request failed after {max_retries} attempts: "
            f"{type(last_exc).__name__}: {last_exc}"
        )
    payload = response.json()
    text = _extract_interaction_text(payload)
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
