from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState


ROOT = Path(__file__).parent
HEALTH_PATH = ROOT / "data" / "workstream_health.json"

# v7 intentionally resets saved browser layout after switching the diagram from
# decorative category colours to implementation-health colours.
FLOW_STATE_KEY = "professional_dashboard_system_flow_state_v7"

STATUS_META = {
    "green": {
        "label": "DONE / WORKING",
        "icon": "🟢",
        "bg": "#F0FDF4",
        "border": "#22C55E",
        "text": "#14532D",
        "edge": "#16A34A",
    },
    "orange": {
        "label": "IN PROGRESS",
        "icon": "🟠",
        "bg": "#FFF7ED",
        "border": "#F59E0B",
        "text": "#7C2D12",
        "edge": "#D97706",
    },
    "red": {
        "label": "NOT WORKING / NOT ACTIVE",
        "icon": "🔴",
        "bg": "#FEF2F2",
        "border": "#EF4444",
        "text": "#7F1D1D",
        "edge": "#DC2626",
    },
}


def _load_health() -> dict:
    fallback = {
        "updated_at": "unknown",
        "legend": {},
        "nodes": {},
        "edges": {},
    }
    try:
        payload = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    return {**fallback, **payload}


HEALTH_CONFIG = _load_health()


def node_health(node_id: str) -> str:
    health = str((HEALTH_CONFIG.get("nodes") or {}).get(node_id, {}).get("health", "orange")).lower()
    return health if health in STATUS_META else "orange"


def node_summary(node_id: str) -> str:
    return str((HEALTH_CONFIG.get("nodes") or {}).get(node_id, {}).get("summary", ""))


def edge_health(edge_id: str) -> str:
    health = str((HEALTH_CONFIG.get("edges") or {}).get(edge_id, "orange")).lower()
    return health if health in STATUS_META else "orange"


def health_text(health: str) -> str:
    meta = STATUS_META.get(health, STATUS_META["orange"])
    return f"{meta['icon']} {meta['label']}"


def workstream_health_counts() -> dict[str, int]:
    counts = {"green": 0, "orange": 0, "red": 0}
    for node_id in "ABCDEFGHIJ":
        counts[node_health(node_id)] += 1
    return counts


WORKSTREAM_DETAILS = {
    "A": {
        "title": "A — Company Intelligence / Relevance",
        "purpose": (
            "Maintain the employer universe and explicit company priority. A answers whether an employer is worth "
            "following; it does not decide whether a specific vacancy is a good semantic fit."
        ),
        "inputs": "User ratings/notes + employers discovered in G + optional feedback evidence from I/H/F.",
        "outputs": "Company universe/context → G and J; discovered employers can be surfaced back into A as Unrated suggestions.",
        "outstanding": "Automate more of the evidence-to-suggestion learning loop without ever overwriting explicit user ratings.",
    },
    "B": {
        "title": "B — Manual Opportunity Intake",
        "purpose": "Capture a role found manually and treat the user's manual add as an explicit positive action rather than sending it back through J.",
        "inputs": "LinkedIn and/or company vacancy URL + optional comment.",
        "outputs": "Manual opportunity → I view; salary research request; employer identity may support A.",
        "outstanding": "Finish canonical direct persistence so the B record is stored as the intended applied/interested lifecycle fact rather than only merged into the I view.",
    },
    "C": {
        "title": "C — Semantic Role Fit",
        "purpose": "Judge only whether the actual day-to-day content of a role is genuinely target work: Strong / Moderate / Weak.",
        "inputs": "Concrete roles from G (plus optional D/E lanes) and explicit role-learning evidence from I. Salary/geography/language/company rating do not determine C.",
        "outputs": "Strong semantic verdicts → actionability → J; learned role concepts can later improve G search intelligence.",
        "outstanding": "Continue draining the unresolved C queue and complete the closed-loop learning/automation around the Work contract.",
    },
    "D": {
        "title": "D — Remote",
        "purpose": "Secondary remote-role discovery lane outside the core permanent-role sourcing engine.",
        "inputs": "Public remote job boards + C target concepts.",
        "outputs": "Optional remote candidate roles → C.",
        "outstanding": "Tighten employability/geography logic and integrate only if the lane continues to add useful candidates.",
    },
    "E": {
        "title": "E — Projects / Interim",
        "purpose": "Secondary project, contract and interim opportunity lane.",
        "inputs": "Project/interim boards and later specialist channels if useful.",
        "outputs": "Optional project/interim candidates → C.",
        "outstanding": "Current pool is sparse; canonical integration remains secondary to the core G→C→J path.",
    },
    "F": {
        "title": "F — People / Network",
        "purpose": "Optional access layer matching contacts to canonical employers without changing intrinsic company or role fit.",
        "inputs": "Connection data + canonical employers from A.",
        "outputs": "Network/access context → A and later prioritisation.",
        "outstanding": "Deferred: there is no live connection dataset and the lane is not active today.",
    },
    "G": {
        "title": "G — Sourcing Engine",
        "purpose": "Aggregate company, consulting, PE, sector and country-board sourcing into a broad deduplicated candidate pool.",
        "inputs": "A employer universe + C search concepts + country weights + configured boards/career sites.",
        "outputs": "Candidate roles → C; newly discovered employers → A suggestions.",
        "outstanding": "Finish source-quality hardening and verify the refreshed production board sweep after the current parser cleanup.",
    },
    "H": {
        "title": "H — Attainability",
        "purpose": "Learn how realistic comparable roles are from actual application outcomes while staying separate from A preference and C semantic fit.",
        "inputs": "Actual lifecycle outcomes from I: application, rejection, interview, case, final, offer, withdrawal.",
        "outputs": "Future attainability context → A/C/G/J without overwriting preference or semantic fit.",
        "outstanding": "Accumulate enough observations and build grouped, confidence-aware inference before using H as a live prioritisation signal.",
    },
    "I": {
        "title": "I — Opportunity & Application History",
        "purpose": "Canonical factual memory of decisions and application lifecycle events. I stores facts; it does not infer fit itself.",
        "inputs": "B manual adds + J Apply/Maybe/Skip + later stage/outcome updates.",
        "outputs": "Preference evidence → A/C and factual outcomes → H.",
        "outstanding": "Finish canonical B persistence/event-log cleanup so all factual lifecycle data has one durable source of truth.",
    },
    "J": {
        "title": "J — Apply Shortlist",
        "purpose": "Final actionable working queue rather than another sourcing board.",
        "inputs": "Promoted C=Strong roles + actionability/quality + A/company context + country/salary context.",
        "outputs": "Apply/Maybe/Skip and feedback → I.",
        "outstanding": "Keep selection quality high and add remaining H/link-health context without weakening the Strong-only semantic gate.",
    },
}


SUPPORT_DETAILS = {
    "COUNTRY": {
        "title": "Country Targeting",
        "purpose": "Soft weights shape sourcing effort and shortlist diversification without forcing weak filler.",
        "inputs": "Target-country weights.",
        "outputs": "Search allocation → G; soft diversification → J.",
        "outstanding": "Maintain as soft guidance only.",
    },
    "QUALITY": {
        "title": "Actionability / Quality",
        "purpose": "Keep language, geography, parser artefacts, dead/weak links and missing enrichment from contaminating J.",
        "inputs": "Vacancy fields, URL, language/geography requirements and enrichment state.",
        "outputs": "Eligibility / warning flags → J.",
        "outstanding": "Unify remaining live-link and enrichment checks; language/actionability and parser-quality guards already work.",
    },
}


EDGE_DETAILS = {
    "A-G": {"flow": "Company universe, explicit priority, category and career URLs feed company-driven sourcing.", "missing": ""},
    "G-A": {"flow": "Employers discovered in G are surfaced in A as Unrated suggestions without overwriting explicit ratings.", "missing": ""},
    "A-C": {"flow": "Company identity accompanies a role into C as context only; A rating does not determine Strong/Moderate/Weak.", "missing": ""},
    "A-J": {"flow": "J can display/use company context when comparing otherwise actionable roles.", "missing": ""},
    "A-F": {"flow": "Canonical employer identities are available for the optional network lane.", "missing": "F itself is not active."},
    "F-A": {"flow": "Matched contacts should provide an optional employer-access signal.", "missing": "No live network data is loaded."},
    "B-A": {"flow": "Manual roles may expose new employer identities to A.", "missing": "Systematic canonical B→A ingestion is not fully finished."},
    "I-A": {"flow": "Company preference evidence from history can inform future A suggestions.", "missing": "Evidence exists, but automatic suggestion calibration is still incomplete."},
    "H-A": {"flow": "H should add employer/employer-type attainability context without changing A preference.", "missing": "Grouped H model is not live."},
    "C-G": {"flow": "C thesis/learning should improve future G search concepts.", "missing": "The closed-loop learning update is not automatic yet."},
    "G-C": {"flow": "Canonical G sends concrete candidate roles into the C semantic queue.", "missing": ""},
    "D-C": {"flow": "Remote roles can use the same C semantic classification.", "missing": "Secondary lane is only partially integrated."},
    "E-C": {"flow": "Project/interim roles can use the same C semantic classification.", "missing": "Secondary lane is sparse and only partially integrated."},
    "I-C": {"flow": "Role-content feedback/history supplies learning evidence for C.", "missing": "Evidence preparation exists; automated thesis update remains intentionally controlled/incomplete."},
    "H-C": {"flow": "H should provide role-family/seniority attainability context without changing semantic fit.", "missing": "Grouped H model is not live."},
    "C-J": {"flow": "Promoted C=Strong and actionable roles feed the live production J pool.", "missing": ""},
    "H-G": {"flow": "H may later soft-reweight search effort toward empirically attainable segments.", "missing": "No live H reweighting yet."},
    "H-J": {"flow": "H should later add separate attainability/confidence context to J prioritisation.", "missing": "No live H signal in J yet."},
    "COUNTRY-G": {"flow": "Country weights guide sourcing effort across target markets.", "missing": ""},
    "COUNTRY-J": {"flow": "Country mix is used as soft diversification after semantic quality/actionability.", "missing": ""},
    "QUALITY-J": {"flow": "Actionability and quality guards filter/warn before J.", "missing": "Unified live-link/enrichment validation is still incomplete."},
    "B-I": {"flow": "Manual B opportunities appear in I immediately.", "missing": "Canonical direct lifecycle persistence still needs cleanup."},
    "J-I": {"flow": "J decisions and feedback are saved into application/opportunity history.", "missing": ""},
    "I-H": {"flow": "Actual stages/outcomes from I create the factual evidence base for H.", "missing": "Inference remains data-limited, but the evidence pipe itself works."},
}

# Keep status available inside EDGE_DETAILS for callers that still expect it.
for _edge_id, _edge_info in EDGE_DETAILS.items():
    _edge_info["status"] = health_text(edge_health(_edge_id))


def _style(health: str, width: int = 230, min_height: int = 125) -> dict:
    c = STATUS_META[health]
    return {
        "background": c["bg"],
        "border": f"2px solid {c['border']}",
        "borderRadius": "12px",
        "padding": "12px 14px",
        "width": f"{width}px",
        "minHeight": f"{min_height}px",
        "color": c["text"],
        "fontSize": "12px",
        "lineHeight": "1.25",
        "boxShadow": "0 3px 12px rgba(15, 23, 42, 0.06)",
    }


def _node(
    node_id: str,
    pos: tuple[int, int],
    title: str,
    description: str,
    *,
    width: int = 230,
    min_height: int = 125,
    source_position: str = "bottom",
    target_position: str = "top",
) -> StreamlitFlowNode:
    health = node_health(node_id)
    meta = STATUS_META[health]
    content = f"### {title}\n{meta['icon']} **{meta['label']}**\n{description}"
    return StreamlitFlowNode(
        id=node_id,
        pos=pos,
        data={"content": content},
        node_type="default",
        source_position=source_position,
        target_position=target_position,
        draggable=True,
        selectable=True,
        connectable=False,
        deletable=False,
        style=_style(health, width, min_height),
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    label: str,
    *,
    kind: str = "data",
) -> StreamlitFlowEdge:
    health = edge_health(edge_id)
    meta = STATUS_META[health]
    color = meta["edge"]
    dashed = kind != "data" or health == "red"
    style = {"stroke": color, "strokeWidth": 2.6}
    if dashed:
        style["strokeDasharray"] = "7 5"
    return StreamlitFlowEdge(
        id=edge_id,
        source=source,
        target=target,
        edge_type="smoothstep",
        marker_end={"type": "arrowclosed", "color": color},
        animated=health == "green" and kind == "data",
        label=f"{meta['icon']} {label}",
        label_style={"fill": color, "fontWeight": 700, "fontSize": 9},
        label_show_bg=True,
        label_bg_style={"fill": "#FFFFFF", "fillOpacity": 0.94},
        style=style,
    )


def _initial_state() -> StreamlitFlowState:
    nodes = [
        _node("A", (70, 40), "A — Company Intelligence", "Employer universe + explicit priority", width=245),
        _node("B", (350, 40), "B — Manual Intake", "Manual role → I; salary research", width=245),
        _node("D", (720, 20), "D — Remote", "Secondary remote candidate lane", width=235),
        _node("E", (990, 20), "E — Projects / Interim", "Secondary project/interim lane", width=245),
        _node("F", (1270, 20), "F — People / Network", "Deferred access/network layer", width=245),
        _node(
            "G",
            (320, 300),
            "G — Aggregated Sourcing Engine",
            "Company + consulting + PE + sector + country boards\n\nCandidate roles → C · discovered employers → A",
            width=800,
            min_height=155,
        ),
        _node(
            "C",
            (500, 550),
            "C — Semantic Role Fit",
            "Actual job content only: Strong / Moderate / Weak\n\nCurrent Work queue + production bridge",
            width=430,
            min_height=160,
        ),
        _node(
            "COUNTRY",
            (70, 700),
            "Country Targeting",
            "Soft search weights + diversification",
            width=240,
            min_height=120,
            source_position="right",
            target_position="right",
        ),
        _node(
            "J",
            (500, 785),
            "J — Apply Shortlist",
            "C=Strong + actionable production pool\n\nApply / Maybe / Skip → I",
            width=430,
            min_height=150,
        ),
        _node(
            "QUALITY",
            (1040, 780),
            "Actionability / Quality",
            "Language + geo + parser quality\nLive-link/enrichment cleanup remains",
            width=265,
            min_height=125,
            source_position="left",
            target_position="left",
        ),
        _node(
            "I",
            (390, 1035),
            "I — Application / History",
            "Factual decisions + lifecycle\n\nPreference evidence → A/C · outcomes → H",
            width=440,
            min_height=165,
        ),
        _node(
            "H",
            (920, 1035),
            "H — Attainability",
            "Outcome evidence works\n\nGrouped inference / feedback signals not live yet",
            width=390,
            min_height=165,
        ),
    ]

    edges = [
        _edge("A-G", "A", "G", "company universe / priority"),
        _edge("G-A", "G", "A", "new employers", kind="feedback"),
        _edge("A-C", "A", "C", "company identity context", kind="context"),
        _edge("A-J", "A", "J", "company context", kind="context"),
        _edge("A-F", "A", "F", "canonical companies", kind="context"),
        _edge("F-A", "F", "A", "optional access signal", kind="feedback"),
        _edge("B-A", "B", "A", "new employer identity", kind="context"),
        _edge("I-A", "I", "A", "company preference evidence", kind="feedback"),
        _edge("H-A", "H", "A", "employer attainability", kind="feedback"),
        _edge("C-G", "C", "G", "future search intelligence", kind="feedback"),
        _edge("G-C", "G", "C", "candidate roles"),
        _edge("D-C", "D", "C", "remote roles", kind="context"),
        _edge("E-C", "E", "C", "project/interim roles", kind="context"),
        _edge("I-C", "I", "C", "role preference learning", kind="feedback"),
        _edge("H-C", "H", "C", "role attainability", kind="feedback"),
        _edge("C-J", "C", "J", "Strong semantic fit"),
        _edge("H-G", "H", "G", "soft search effort", kind="feedback"),
        _edge("H-J", "H", "J", "attainability context", kind="feedback"),
        _edge("COUNTRY-G", "COUNTRY", "G", "search weights", kind="context"),
        _edge("COUNTRY-J", "COUNTRY", "J", "diversification", kind="context"),
        _edge("QUALITY-J", "QUALITY", "J", "actionability gate"),
        _edge("B-I", "B", "I", "manual opportunity"),
        _edge("J-I", "J", "I", "decision + feedback"),
        _edge("I-H", "I", "H", "actual stages + outcomes"),
    ]
    return StreamlitFlowState(nodes, edges)


def _reset_flow() -> None:
    st.session_state[FLOW_STATE_KEY] = _initial_state()


def _render_detail(selected_id: str | None) -> None:
    edge_info = EDGE_DETAILS.get(selected_id or "")
    if edge_info:
        health = edge_health(selected_id or "")
        st.markdown(f"### Connection {selected_id}")
        st.markdown(f"**{health_text(health)}**")
        st.markdown(edge_info["flow"])
        if edge_info["missing"]:
            st.markdown(f"**Remaining:** {edge_info['missing']}")
        return

    info = WORKSTREAM_DETAILS.get(selected_id or "") or SUPPORT_DETAILS.get(selected_id or "")
    if info:
        health = node_health(selected_id or "")
        st.markdown(f"### {info['title']}")
        st.markdown(f"**{health_text(health)}**")
        summary = node_summary(selected_id or "")
        if summary:
            st.caption(summary)
        st.markdown(info["purpose"])
        st.markdown(f"**Inputs**  \n{info['inputs']}")
        st.markdown(f"**Outputs**  \n{info['outputs']}")
        st.markdown(f"**Remaining**  \n{info['outstanding']}")
    else:
        st.info("Click a node or connection to inspect what it does and whether it is actually implemented.")


def render_system_flow() -> None:
    st.markdown('<div class="eyebrow">System architecture</div>', unsafe_allow_html=True)
    st.title("A–J System Flow")
    st.caption(
        f"Implementation health from data/workstream_health.json · updated {HEALTH_CONFIG.get('updated_at', 'unknown')}"
    )

    counts = workstream_health_counts()
    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 Done / working", counts["green"])
    m2.metric("🟠 In progress", counts["orange"])
    m3.metric("🔴 Not working", counts["red"])

    control1, control2, control3, _ = st.columns([1, 1, 1, 4])
    with control1:
        focus = st.toggle("Focus mode", value=True, key="system_flow_focus")
    with control2:
        show_details = st.toggle("Details / legend", value=False, key="system_flow_details")
    with control3:
        if st.button("Reset layout", use_container_width=True):
            _reset_flow()
            st.rerun()

    if focus:
        st.markdown(
            """
            <style>
              [data-testid="stSidebar"] {display: none !important;}
              .block-container {max-width: 100% !important; padding-left: 1rem !important; padding-right: 1rem !important;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    if FLOW_STATE_KEY not in st.session_state:
        st.session_state[FLOW_STATE_KEY] = _initial_state()

    if show_details:
        canvas, detail = st.columns([5.2, 1.3], gap="medium")
    else:
        canvas = st.container()
        detail = None

    with canvas:
        st.session_state[FLOW_STATE_KEY] = streamlit_flow(
            "professional_dashboard_system_flow_v7",
            st.session_state[FLOW_STATE_KEY],
            fit_view=True,
            height=1080 if focus else 980,
            show_controls=True,
            show_minimap=True,
            hide_watermark=True,
            allow_new_edges=False,
            enable_node_menu=False,
            enable_edge_menu=False,
            enable_pane_menu=False,
            get_node_on_click=True,
            get_edge_on_click=True,
            min_zoom=0.18,
        )

    selected_id = getattr(st.session_state[FLOW_STATE_KEY], "selected_id", None)
    if detail is not None:
        with detail:
            st.subheader("Selected")
            _render_detail(selected_id)
            st.divider()
            st.markdown("#### Health legend")
            st.markdown(
                "🟢 **DONE / WORKING** — intended flow is implemented  \n"
                "🟠 **IN PROGRESS** — mostly working, but integration/cleanup remains  \n"
                "🔴 **NOT WORKING / NOT ACTIVE** — missing, deferred or not wired"
            )
            st.caption("Solid = core candidate/data flow. Dashed = context, feedback, secondary or inactive relation.")
