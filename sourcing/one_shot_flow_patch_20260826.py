from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing patch anchor: {label}")
    return text.replace(old, new, 1)


# 1) B UI: B is a manual application lane, not merely Interested.
b_path = "add_opportunity_ui.py"
b = read(b_path)
for old, new in [
    (
        "Paste a role you found yourself. Saving it means Interested: it enters I immediately. ",
        "Paste a role you already applied to yourself. Saving it means Applied: it enters I immediately. ",
    ),
    (
        "B is an intentional manual-intake lane. A role you actively add is automatically treated as Interested, ",
        "B is an intentional manual-application lane. A role you add here is automatically treated as Applied, ",
    ),
    ("Add as Interested", "Add as Applied"),
    ('"feedback": "Interested"', '"feedback": "Applied"'),
    ('"Add Interested opportunity"', '"Add Applied opportunity"'),
    (
        "Saved as Interested and sent to I. Zero-cost salary research is queued.",
        "Saved as Applied and sent to I. Zero-cost salary research is queued.",
    ),
    (
        "Intent is always Interested. Salary research is read-only here; only your comment remains editable.",
        "Application status is Applied in B. Salary research is read-only here; only your comment remains editable.",
    ),
    ('updated.loc[shared, "feedback"] = "Interested"', 'updated.loc[shared, "feedback"] = "Applied"'),
]:
    b = b.replace(old, new)
write(b_path, b)


# 1) I UI: expose the append-only canonical event history.
i_path = "opportunity_history_ui.py"
i = read(i_path)
if 'EVENT_PATH = DATA_DIR / "opportunity_events.csv"' not in i:
    i = replace_once(
        i,
        'HISTORY_PATH = "data/opportunity_history.csv"\nB_PATH = DATA_DIR / "user_submitted_opportunities.csv"',
        'HISTORY_PATH = "data/opportunity_history.csv"\nEVENT_PATH = DATA_DIR / "opportunity_events.csv"\nB_PATH = DATA_DIR / "user_submitted_opportunities.csv"',
        "I event path",
    )
if "Canonical I event timeline" not in i:
    tail = '    h3.metric("Reached final / offer", int(applications["application_stage"].isin(FINAL_REACHED_STAGES).sum()))'
    timeline = tail + '''

    st.divider()
    with st.expander("Canonical I event timeline", expanded=False):
        st.caption(
            "Append-only audit history generated from B/J decisions and application-stage changes. "
            "The tracker above is the current latest state; this timeline preserves how it changed."
        )
        if not EVENT_PATH.exists() or not EVENT_PATH.stat().st_size:
            st.info("No canonical I events have been generated yet.")
        else:
            try:
                events = pd.read_csv(EVENT_PATH).fillna("")
            except Exception:
                st.warning("The canonical event log could not be loaded.")
            else:
                if events.empty:
                    st.info("No canonical I events have been generated yet.")
                else:
                    events["_sort"] = pd.to_datetime(events.get("event_at", ""), errors="coerce", utc=True)
                    events = events.sort_values(
                        ["_sort", "event_id"], ascending=[False, False], na_position="last"
                    ).drop(columns="_sort")
                    st.dataframe(
                        events[[
                            "event_at", "event_type", "source_stream", "action", "application_stage",
                            "company_feedback", "role_feedback", "user_comment", "outcome_reason", "notes",
                        ]],
                        hide_index=True,
                        width="stretch",
                        height=420,
                    )
'''
    i = replace_once(i, tail, timeline, "I event timeline")
write(i_path, i)


# 3) B -> A: generate separate Unrated employer suggestions from manual applications.
builder = textwrap.dedent(r'''
    """Build A company suggestions from manual B applications.

    B is application intake. Discovering a company through B should make that
    employer visible to A, but must never assign an A/B/C/Exclude rating.
    """
    from __future__ import annotations

    import argparse
    import re
    from pathlib import Path

    import pandas as pd

    from sourcing.g_data_quality import invalid_company_name, invalid_job_title

    ROOT = Path(__file__).resolve().parents[1]
    SUBMISSIONS = ROOT / "data" / "user_submitted_opportunities.csv"
    RESEARCH = ROOT / "data" / "user_submitted_opportunity_research.csv"
    OUT = ROOT / "data" / "a_b_discovered_companies.csv"

    OUT_COLUMNS = [
        "suggested_company_id", "company", "role_count", "countries", "source_streams",
        "sample_titles", "first_seen_at", "last_seen_at", "suggested_rating", "evidence_source",
    ]


    def _clean(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()


    def _slug(value: object) -> str:
        text = re.sub(r"[^a-z0-9]+", "-", _clean(value).lower()).strip("-")
        return text or "b-discovered-company"


    def _overlay_research(submissions: pd.DataFrame, research: pd.DataFrame) -> pd.DataFrame:
        out = submissions.fillna("").copy()
        if out.empty or research.empty or "submission_id" not in out.columns or "submission_id" not in research.columns:
            return out
        latest = research.fillna("").drop_duplicates("submission_id", keep="last").set_index("submission_id")
        for col in ["company", "canonical_company_id", "country", "title", "location"]:
            if col not in latest.columns:
                continue
            if col not in out.columns:
                out[col] = ""
            mapped = out["submission_id"].map(latest[col]).fillna("")
            out[col] = mapped.where(mapped.astype(str).str.strip().ne(""), out[col].fillna(""))
        return out


    def build_suggestions(submissions: pd.DataFrame, research: pd.DataFrame | None = None) -> pd.DataFrame:
        if submissions.empty:
            return pd.DataFrame(columns=OUT_COLUMNS)
        frame = _overlay_research(submissions, research if research is not None else pd.DataFrame())
        for col in ["submission_id", "submitted_at", "company", "canonical_company_id", "country", "title"]:
            if col not in frame.columns:
                frame[col] = ""
        frame = frame.fillna("")
        frame["company"] = frame["company"].map(_clean)
        frame["title"] = frame["title"].map(_clean)
        frame = frame[frame["company"].ne("") & ~frame["company"].map(invalid_company_name)].copy()
        if frame.empty:
            return pd.DataFrame(columns=OUT_COLUMNS)
        frame["suggested_company_id"] = frame.apply(
            lambda row: _clean(row.get("canonical_company_id", "")) or _slug(row.get("company", "")), axis=1
        )
        rows: list[dict[str, object]] = []
        for company_id, group in frame.groupby("suggested_company_id", sort=False):
            group = group.copy()
            titles = []
            for value in group["title"]:
                title = _clean(value)
                if title and not invalid_job_title(title) and title not in titles:
                    titles.append(title)
            if not titles:
                titles = ["Manual application"]
            countries = []
            for value in group["country"]:
                country = _clean(value)
                if country and country not in countries:
                    countries.append(country)
            timestamps = [_clean(x) for x in group["submitted_at"] if _clean(x)]
            rows.append({
                "suggested_company_id": company_id,
                "company": _clean(group.iloc[-1]["company"]),
                "role_count": int(group["submission_id"].astype(str).nunique()),
                "countries": "; ".join(countries),
                "source_streams": "B",
                "sample_titles": " | ".join(titles[:5]),
                "first_seen_at": min(timestamps) if timestamps else "",
                "last_seen_at": max(timestamps) if timestamps else "",
                "suggested_rating": "Unrated",
                "evidence_source": "B manual application",
            })
        return pd.DataFrame(rows).reindex(columns=OUT_COLUMNS, fill_value="").sort_values(
            ["last_seen_at", "company"], ascending=[False, True]
        ).reset_index(drop=True)


    def _read_csv(path: Path) -> pd.DataFrame:
        if not path.exists() or not path.stat().st_size:
            return pd.DataFrame()
        try:
            return pd.read_csv(path).fillna("")
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            return pd.DataFrame()


    def main() -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--submissions", default=str(SUBMISSIONS))
        parser.add_argument("--research", default=str(RESEARCH))
        parser.add_argument("--out", default=str(OUT))
        args = parser.parse_args()
        result = build_suggestions(_read_csv(Path(args.submissions)), _read_csv(Path(args.research)))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(out, index=False)
        print(f"wrote {len(result)} B-discovered company suggestions to {out}")


    if __name__ == "__main__":
        main()
''').lstrip()
write("sourcing/build_b_company_suggestions.py", builder)

builder_test = textwrap.dedent(r'''
    from __future__ import annotations

    import unittest
    import pandas as pd

    from sourcing.build_b_company_suggestions import build_suggestions


    class BCompanySuggestionTests(unittest.TestCase):
        def test_manual_application_becomes_unrated_a_suggestion(self) -> None:
            submissions = pd.DataFrame([{
                "submission_id": "1", "submitted_at": "2026-08-26T10:00:00+00:00",
                "company": "Example Treasury AG", "canonical_company_id": "example-treasury",
                "country": "Germany", "title": "Treasury Analyst",
            }])
            out = build_suggestions(submissions)
            self.assertEqual(len(out), 1)
            row = out.iloc[0]
            self.assertEqual(row["suggested_company_id"], "example-treasury")
            self.assertEqual(row["suggested_rating"], "Unrated")
            self.assertEqual(row["source_streams"], "B")

        def test_research_can_fill_missing_company_identity(self) -> None:
            submissions = pd.DataFrame([{
                "submission_id": "1", "submitted_at": "2026-08-26T10:00:00+00:00",
                "company": "", "canonical_company_id": "", "country": "", "title": "",
            }])
            research = pd.DataFrame([{
                "submission_id": "1", "company": "Research Filled plc",
                "canonical_company_id": "research-filled", "country": "United Kingdom",
                "title": "Corporate Finance Analyst",
            }])
            out = build_suggestions(submissions, research)
            self.assertEqual(out.iloc[0]["suggested_company_id"], "research-filled")
            self.assertIn("Corporate Finance Analyst", out.iloc[0]["sample_titles"])


    if __name__ == "__main__":
        unittest.main()
''').lstrip()
write("sourcing/test_b_company_suggestions.py", builder_test)


# A UI reads G and B discovery lanes together; explicit rating remains authoritative.
a_path = "company_targeting_ui.py"
a = read(a_path)
a = replace_once(
    a,
    'DISCOVERED_COMPANIES_PATH = Path(__file__).parent / "data" / "a_discovered_companies.csv"',
    'DISCOVERED_COMPANIES_PATHS = [\n    Path(__file__).parent / "data" / "a_discovered_companies.csv",\n    Path(__file__).parent / "data" / "a_b_discovered_companies.csv",\n]',
    "A discovery paths",
)
if "def _load_discovered_company_suggestions" not in a:
    marker = "\ndef _usable_suggestion(row: pd.Series, known_names: set[str]) -> bool:\n"
    helper = r'''

def _split_values(value: object, separator: str) -> list[str]:
    return [x.strip() for x in str(value or "").split(separator) if x.strip()]


def _load_discovered_company_suggestions() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in DISCOVERED_COMPANIES_PATHS:
        if not path.exists() or not path.stat().st_size:
            continue
        try:
            frame = pd.read_csv(path).fillna("").reindex(columns=DISCOVERED_COLUMNS, fill_value="")
        except Exception:
            continue
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=DISCOVERED_COLUMNS)

    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    rows: list[pd.Series] = []
    for _, group in combined.groupby("suggested_company_id", sort=False):
        ranked = group.sort_values("last_seen_at", ascending=True)
        row = ranked.iloc[-1].copy()
        row["role_count"] = int(pd.to_numeric(group["role_count"], errors="coerce").fillna(0).sum())
        countries: list[str] = []
        streams: list[str] = []
        titles: list[str] = []
        evidence: list[str] = []
        for value in group["countries"]:
            for item in _split_values(value, ";"):
                if item not in countries:
                    countries.append(item)
        for value in group["source_streams"]:
            for item in _split_values(value, ";"):
                if item not in streams:
                    streams.append(item)
        for value in group["sample_titles"]:
            for item in _split_values(value, "|"):
                if item not in titles:
                    titles.append(item)
        for value in group["evidence_source"]:
            item = str(value or "").strip()
            if item and item not in evidence:
                evidence.append(item)
        row["countries"] = "; ".join(countries)
        row["source_streams"] = "; ".join(streams)
        row["sample_titles"] = " | ".join(titles[:6])
        row["evidence_source"] = "; ".join(evidence)
        first = [str(x).strip() for x in group["first_seen_at"] if str(x).strip()]
        last = [str(x).strip() for x in group["last_seen_at"] if str(x).strip()]
        row["first_seen_at"] = min(first) if first else ""
        row["last_seen_at"] = max(last) if last else ""
        row["suggested_rating"] = "Unrated"
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=DISCOVERED_COLUMNS, fill_value="")
'''
    a = replace_once(a, marker, helper + marker, "A combined discovery helper")
old_loader = '''def render_discovered_company_suggestions() -> None:
    """Show G-discovered employers as A suggestions without auto-rating them."""
    if not DISCOVERED_COMPANIES_PATH.exists() or not DISCOVERED_COMPANIES_PATH.stat().st_size:
        return
    try:
        discovered = pd.read_csv(DISCOVERED_COMPANIES_PATH).fillna("").reindex(columns=DISCOVERED_COLUMNS, fill_value="")
    except Exception:
        return
    if discovered.empty:
        return
'''
new_loader = '''def render_discovered_company_suggestions() -> None:
    """Show G/B-discovered employers as A suggestions without auto-rating them."""
    discovered = _load_discovered_company_suggestions()
    if discovered.empty:
        return
'''
a = replace_once(a, old_loader, new_loader, "A discovery loader")
a = a.replace('"archetype": "G-discovered employer"', '"archetype": "Discovered employer"')
a = a.replace('"source_strategy": "G discovery → explicit A review"', '"source_strategy": "G/B discovery → explicit A review"')
a = a.replace('"notes": "Promoted from G after explicit A rating."', '"notes": "Promoted from discovery after explicit A rating."')
a = a.replace('"company_category": "Unclassified / G discovered"', '"company_category": "Unclassified / discovered"')
a = a.replace('"G-discovered employer; explicitly rated in A."', '"Discovered employer; explicitly rated in A."')
a = a.replace("Discovered by G", "Discovered by G / B", 1)
a = a.replace(
    "New employers found while sourcing vacancies. They enter A only as Unrated suggestions. ",
    "New employers found by G or through a manual B application. They enter A only as Unrated suggestions. ",
    1,
)
a = a.replace('"role_count": st.column_config.NumberColumn("G roles", width="small")', '"role_count": st.column_config.NumberColumn("Evidence roles", width="small")')
a = a.replace('"sample_titles": st.column_config.TextColumn("Why G found it", width="large")', '"sample_titles": st.column_config.TextColumn("Why it was found", width="large")')
write(a_path, a)


# Keep B->A suggestions regenerated alongside canonical I.
sync_path = ".github/workflows/i-learning-sync.yml"
sync = read(sync_path)
if 'sourcing/build_b_company_suggestions.py' not in sync:
    sync = replace_once(
        sync,
        '      - "sourcing/test_reconcile_i_learning.py"\n',
        '      - "sourcing/test_reconcile_i_learning.py"\n      - "sourcing/build_b_company_suggestions.py"\n      - "sourcing/test_b_company_suggestions.py"\n',
        "I sync B suggestion paths",
    )
    sync = sync.replace(
        'run: python -m unittest sourcing.test_reconcile_i_learning',
        'run: python -m unittest sourcing.test_reconcile_i_learning sourcing.test_b_company_suggestions',
        1,
    )
    anchor = '            --h-summary-out data/h_learning_summary.csv\n      - name: Commit canonical I and learning outputs'
    replacement = '            --h-summary-out data/h_learning_summary.csv\n      - name: Build B-discovered A suggestions\n        run: python -m sourcing.build_b_company_suggestions\n      - name: Commit canonical I and learning outputs'
    sync = replace_once(sync, anchor, replacement, "I sync builder step")
    sync = replace_once(
        sync,
        '            data/h_learning_summary.csv\n',
        '            data/h_learning_summary.csv \\\n            data/a_b_discovered_companies.csv\n',
        "I sync git add B suggestions",
    )
write(sync_path, sync)

quality_path = ".github/workflows/i-learning-quality.yml"
quality = read(quality_path)
if 'sourcing/build_b_company_suggestions.py' not in quality:
    quality = replace_once(
        quality,
        '      - "sourcing/test_reconcile_i_learning.py"\n',
        '      - "sourcing/test_reconcile_i_learning.py"\n      - "sourcing/build_b_company_suggestions.py"\n      - "sourcing/test_b_company_suggestions.py"\n',
        "I quality B suggestion paths",
    )
    quality = quality.replace(
        'run: python -m unittest sourcing.test_reconcile_i_learning',
        'run: python -m unittest sourcing.test_reconcile_i_learning sourcing.test_b_company_suggestions',
        1,
    )
    anchor = '            --h-summary-out /tmp/i-sync/h_learning_summary.csv\n          python - <<\'PY\''
    replacement = '            --h-summary-out /tmp/i-sync/h_learning_summary.csv\n          python -m sourcing.build_b_company_suggestions --out /tmp/i-sync/a_b_discovered_companies.csv\n          python - <<\'PY\''
    quality = replace_once(quality, anchor, replacement, "I quality builder dry-run")
write(quality_path, quality)


# 4) C -> G: explicit, soft sourcing guidance contract.
contract = textwrap.dedent('''
    # C → G Sourcing Learning Contract

    ## Purpose
    C owns semantic role fit. G owns recall and sourcing. C may teach G which role
    families deserve more search effort, but C feedback must never silently become
    a hard exclusion rule in G.

    ## Source of truth
    Structured guidance lives in `data/c_to_g_sourcing_guidance.csv` with columns:

    - `guidance_id` — stable identifier.
    - `status` — `Proposed`, `Active`, or `Retired`.
    - `direction` — `prioritize` or `deprioritize`.
    - `query_term` — concrete extra G search query when direction is `prioritize`.
    - `role_family` — human-readable semantic family.
    - `rationale` — concise evidence-based explanation.
    - `evidence_count` — number of C examples supporting the pattern.
    - `updated_at` — ISO timestamp.

    ## Production behavior
    Only rows with `status=Active`, `direction=prioritize`, and a non-empty
    `query_term` are consumed automatically. Their query terms are appended to G's
    board search vocabulary and deduplicated. Existing G queries remain intact.

    `deprioritize` guidance is deliberately **soft evidence only**. It is recorded
    for future source-budget tuning but never removes vacancies or prevents them
    reaching C. This protects recall and keeps semantic judgement inside C.

    ## C Work rules
    - During QC/recalibration, recurring false positives or missing target families
      may be written as `Proposed` guidance.
    - Do not activate a guidance row merely because of one ambiguous title.
    - `Active` should represent an explicit, stable semantic conclusion consistent
      with `docs/C_SEMANTIC_THESIS.md`.
    - Salary, language, geography, link health, company attractiveness and
      attainability never belong in this file.
    - Free-text I comments are evidence, not automatic query instructions.
    - Never mutate the C thesis silently in order to create G guidance.

    ## Examples
    A repeated finding that direct `deal finance` roles are under-sourced can become
    an Active `prioritize` row with `query_term=deal finance`.

    A repeated finding that AI/software engineering inside CIB is semantically Weak
    may be recorded as `deprioritize`, but G must not hard-filter all AI/data titles
    because some finance roles legitimately use those tools.
''').lstrip()
write("docs/C_TO_G_LEARNING_CONTRACT.md", contract)

guidance_path = ROOT / "data" / "c_to_g_sourcing_guidance.csv"
if not guidance_path.exists():
    write(
        "data/c_to_g_sourcing_guidance.csv",
        "guidance_id,status,direction,query_term,role_family,rationale,evidence_count,updated_at\n",
    )

guidance_module = textwrap.dedent(r'''
    """Safe C -> G sourcing guidance loader.

    C may add search coverage, but this module never hard-filters G candidates.
    """
    from __future__ import annotations

    import re
    from pathlib import Path
    import pandas as pd

    ROOT = Path(__file__).resolve().parents[1]
    GUIDANCE_PATH = ROOT / "data" / "c_to_g_sourcing_guidance.csv"


    def _clean(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()


    def priority_queries_from_frame(frame: pd.DataFrame) -> list[str]:
        if frame.empty:
            return []
        data = frame.fillna("").copy()
        for col in ["status", "direction", "query_term"]:
            if col not in data.columns:
                return []
        active = data[
            data["status"].astype(str).str.strip().str.lower().eq("active")
            & data["direction"].astype(str).str.strip().str.lower().eq("prioritize")
        ]
        queries: list[str] = []
        seen: set[str] = set()
        for value in active["query_term"]:
            query = _clean(value)
            key = query.casefold()
            if query and key not in seen:
                queries.append(query)
                seen.add(key)
        return queries


    def active_priority_queries(path: Path = GUIDANCE_PATH) -> list[str]:
        if not path.exists() or not path.stat().st_size:
            return []
        try:
            frame = pd.read_csv(path).fillna("")
        except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
            return []
        return priority_queries_from_frame(frame)
''').lstrip()
write("sourcing/c_to_g_guidance.py", guidance_module)

guidance_test = textwrap.dedent(r'''
    from __future__ import annotations

    import unittest
    import pandas as pd

    from sourcing.c_to_g_guidance import priority_queries_from_frame


    class CToGGuidanceTests(unittest.TestCase):
        def test_only_active_prioritize_rows_add_queries(self) -> None:
            frame = pd.DataFrame([
                {"status": "Active", "direction": "prioritize", "query_term": "deal finance"},
                {"status": "Proposed", "direction": "prioritize", "query_term": "portfolio construction"},
                {"status": "Active", "direction": "deprioritize", "query_term": "AI engineer"},
                {"status": "Active", "direction": "prioritize", "query_term": "Deal Finance"},
            ])
            self.assertEqual(priority_queries_from_frame(frame), ["deal finance"])


    if __name__ == "__main__":
        unittest.main()
''').lstrip()
write("sourcing/test_c_to_g_guidance.py", guidance_test)


# Wire only positive, explicitly Active C guidance into the production board query vocabulary.
g_path = "sourcing/board_sweep_v2.py"
g = read(g_path)
if "from sourcing.c_to_g_guidance import active_priority_queries" not in g:
    g = replace_once(
        g,
        "from sourcing.big4_pilot import calibrate_jobs\n",
        "from sourcing.big4_pilot import calibrate_jobs\nfrom sourcing.c_to_g_guidance import active_priority_queries\n",
        "G guidance import",
    )
    start = g.index("def _run_board(")
    end = g.index("\ndef main()", start)
    block = g[start:end]
    block = block.replace(
        "def _run_board(row: object, per_query: int, max_details: int) -> tuple[list[dict], list[str]]:",
        "def _run_board(row: object, per_query: int, max_details: int, queries: list[str]) -> tuple[list[dict], list[str]]:",
        1,
    )
    block = block.replace("SEARCH_QUERIES", "queries")
    g = g[:start] + block + g[end:]
    g = replace_once(
        g,
        "    budgets = _country_board_budgets(runnable, args.per_query, args.max_details)\n",
        "    budgets = _country_board_budgets(runnable, args.per_query, args.max_details)\n    search_queries = list(dict.fromkeys([*SEARCH_QUERIES, *active_priority_queries()]))\n",
        "G dynamic query set",
    )
    g = replace_once(
        g,
        "            found, errors = _run_board(row, board_per_query, board_max_details)",
        "            found, errors = _run_board(row, board_per_query, board_max_details, search_queries)",
        "G run board query argument",
    )
    g = g.replace('"queries": len(SEARCH_QUERIES)', '"queries": len(search_queries)')
write(g_path, g)

board_wf_path = ".github/workflows/board-sourcing.yml"
board_wf = read(board_wf_path)
if 'sourcing/c_to_g_guidance.py' not in board_wf:
    board_wf = replace_once(
        board_wf,
        '      - "sourcing/board_sweep_v2.py"\n',
        '      - "sourcing/board_sweep_v2.py"\n      - "sourcing/c_to_g_guidance.py"\n      - "sourcing/test_c_to_g_guidance.py"\n      - "data/c_to_g_sourcing_guidance.csv"\n      - "docs/C_TO_G_LEARNING_CONTRACT.md"\n',
        "G workflow guidance paths",
    )
    old = "python -m unittest sourcing.test_filter_language_requirements sourcing.test_board_html_adapters"
    new = "python -m unittest sourcing.test_c_to_g_guidance sourcing.test_filter_language_requirements sourcing.test_board_html_adapters"
    board_wf = replace_once(board_wf, old, new, "G workflow guidance test")
write(board_wf_path, board_wf)


# Health map: B -> A is now a live Unrated suggestion path. C -> G stays orange until
# C Work produces stable Active guidance rows.
health_path = ROOT / "data" / "workstream_health.json"
health = json.loads(health_path.read_text(encoding="utf-8"))
health["edges"]["B-A"] = "green"
health["edges"]["C-G"] = "orange"
health["nodes"]["B"]["summary"] = "Manual applications reconcile to canonical I as Apply / Applied; B-discovered employers also surface in A as Unrated suggestions."
health["nodes"]["G"]["summary"] = "Broad sourcing is live; approved C prioritize guidance can extend search coverage, while source/link quality maintenance remains in progress."
health_path.write_text(json.dumps(health, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# Generate the current B -> A suggestion snapshot now and validate the patch.
subprocess.run(["python", "-m", "sourcing.build_b_company_suggestions"], cwd=ROOT, check=True)
subprocess.run(
    [
        "python", "-m", "unittest",
        "sourcing.test_b_company_suggestions",
        "sourcing.test_c_to_g_guidance",
        "sourcing.test_reconcile_i_learning",
    ],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [
        "python", "-m", "py_compile",
        "add_opportunity_ui.py",
        "opportunity_history_ui.py",
        "company_targeting_ui.py",
        "sourcing/build_b_company_suggestions.py",
        "sourcing/c_to_g_guidance.py",
        "sourcing/board_sweep_v2.py",
    ],
    cwd=ROOT,
    check=True,
)
print("one-shot flow patch completed")
