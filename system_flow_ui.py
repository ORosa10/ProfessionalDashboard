from __future__ import annotations

import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState


# v2 intentionally resets old browser layout so newly added/changed connections appear.
FLOW_STATE_KEY = "professional_dashboard_system_flow_state_v2"


WORKSTREAM_DETAILS = {
    "A": {
        "title": "A — Company Intelligence / Relevance",
        "status": "🟡 Core works; learning loop incomplete",
        "purpose": (
            "Maintain the employer universe and company priority. A answers whether an employer is worth "
            "systematically following; it does NOT decide whether a specific role is a good fit."
        ),
        "inputs": (
            "User → explicit A/B/C/Exclude + notes; B → manually discovered company/company signal; "
            "G → newly discovered employers; I → historical company feedback; H → later hiring outcomes; "
            "F → network/access signal."
        ),
        "outputs": (
            "A → G: company universe, priority, career URLs and category for sourcing. "
            "A → C/J: company rating/context only (not a hard role gate). "
            "A → F: canonical companies/aliases for contact matching."
        ),
        "outstanding": (
            "Add Suggested A/B/C/Exclude from historical company evidence and ingest newly discovered employers "
            "from G/B without overwriting explicit user ratings."
        ),
    },
    "B": {
        "title": "B — Manual Opportunity Intake",
        "status": "🟢 Working",
        "purpose": "Capture a role found manually and enrich it once, without forcing a duplicate decision in J.",
        "inputs": "LinkedIn and/or company job URL + optional comment.",
        "outputs": "Enriched opportunity → I; company signal → A; role signal → C.",
        "outstanding": "Every new enrichment must include role/company context + researched salary range + salary expectation.",
    },
    "C": {
        "title": "C — Semantic Fit",
        "status": "🟡 Calibrated; canonical store needs cleanup",
        "purpose": "Judge actual job responsibilities against the targeting thesis: Strong / Moderate / Weak.",
        "inputs": "Candidate roles from G/D/E; company context from A; historical feedback from I/H; manual evidence from B.",
        "outputs": "Canonical semantic judgement; actionable Strong roles → J; targeting thesis → G.",
        "outstanding": "Consolidate curated J judgements back into canonical semantic-fit data and remove parallel truths.",
    },
    "D": {
        "title": "D — Remote",
        "status": "🟢 Running / secondary",
        "purpose": "Automated remote-role exploration, secondary to the core permanent-role pipeline.",
        "inputs": "Public remote job boards.",
        "outputs": "Remote candidate roles for semantic review.",
        "outstanding": "Tighten Europe/employability filter so US-only remote roles do not create noise.",
    },
    "E": {
        "title": "E — Projects / Interim",
        "status": "🟡 Running / sparse",
        "purpose": "Source contract, interim, freelance and project finance work as a separate lane.",
        "inputs": "Remote/project boards; later tender channels if useful.",
        "outputs": "Project/interim candidates for semantic review and tracking.",
        "outstanding": "Current result pool is sparse; expand sources only if this lane becomes a real priority.",
    },
    "F": {
        "title": "F — People / Network",
        "status": "⚪ Ready / deferred",
        "purpose": "Match LinkedIn connections to canonical employers and provide an access signal without overriding intrinsic fit.",
        "inputs": "LinkedIn Connections CSV + canonical companies from A.",
        "outputs": "Access/network context → A and later opportunity prioritisation.",
        "outstanding": "No connection data loaded yet; activate when networking becomes useful.",
    },
    "G": {
        "title": "G — Sourcing Engine",
        "status": "🟡 Sources run; integration incomplete",
        "purpose": "Aggregate company, PE, consulting, sector and country-board sourcing into one broad candidate pool.",
        "inputs": "A company universe + C targeting thesis + country weights + configured boards/career sites.",
        "outputs": "Deduplicated, language-feasible candidate pool → C; newly discovered employers → A (target state).",
        "outstanding": "Unify separate staging branches and repair/verify the daily country-board run so all sourcing can reach C/J.",
    },
    "H": {
        "title": "H — Attainability",
        "status": "🟡 Early / data-limited",
        "purpose": "Infer realistic chance of landing similar roles from actual application outcomes, separately from preference fit.",
        "inputs": "Application stages and outcomes from I.",
        "outputs": "Attainability evidence → future A/C calibration.",
        "outstanding": "Accumulate enough interviews/rejections/cases/offers before making model-like inferences.",
    },
    "I": {
        "title": "I — Opportunity & Application History",
        "status": "🟢 Working",
        "purpose": "Single factual memory of decisions and application lifecycle for manual and sourced opportunities.",
        "inputs": "B decisions; J Apply/Maybe/Skip; later application-stage updates.",
        "outputs": "Company/role feedback → A/C; stages/outcomes → H.",
        "outstanding": "Keep application stages current; J feedback now auto-saves successfully.",
    },
    "J": {
        "title": "J — Apply Shortlist",
        "status": "🟢 Working; selection logic still evolving",
        "purpose": "Final working queue of genuinely actionable roles, with salary context, links and feedback controls.",
        "inputs": "Semantic fit from C + company context from A + country guidance + salary research.",
        "outputs": "Apply/Maybe/Skip + company/role feedback → I.",
        "outstanding": "Move to Strong-only, integrate country weights jointly with quality, and add link-health checks.",
    },
}


SUPPORT_DETAILS = {
    "COUNTRY": {
        "title": "Country Targeting",
        "status": "Guidance",
        "purpose": "Soft country weights shape search effort and shortlist diversification among good roles; never force weak filler.",
        "inputs": "Target-country weights.",
        "outputs": "Search allocation → G; shortlist diversification → J.",
        "outstanding": "Use jointly with semantic quality rather than only as a replenishment fallback.",
    },
    "QUALITY": {
        "title": "Link & Data Quality",
        "status": "Not built",
        "purpose": "Prevent dead links or missing salary/context from reaching the final shortlist unnoticed.",
        "inputs": "Job URL, salary enrichment, required fields.",
        "outputs": "Quality flags / gate → J.",
        "outstanding": "Add live-link check and salary-present check before J.",
    },
}


EDGE_DETAILS = {
    "A-G": {"status": "LIVE", "flow": "Company universe, priority, category and career URLs feed company-driven sourcing.", "missing": ""},
    "G-A": {"status": "PLANNED", "flow": "New employers discovered while sourcing should be added/enriched in A.", "missing": "No systematic G → A employer-ingestion loop yet."},
    "A-C": {"status": "PARTIAL", "flow": "Company rating/context is available to semantic review as context, never as a hard gate.", "missing": "Canonical C integration is not yet fully consolidated."},
    "A-J": {"status": "LIVE", "flow": "J can display/use company rating/context when comparing otherwise good roles.", "missing": ""},
    "A-F": {"status": "LIVE", "flow": "Canonical company IDs/aliases are used to match uploaded network contacts.", "missing": "F currently has no uploaded connection data."},
    "F-A": {"status": "PARTIAL", "flow": "Matched contacts can provide an access signal for companies.", "missing": "No network data loaded, so the signal is operationally inactive."},
    "B-A": {"status": "PARTIAL", "flow": "Manual opportunities expose employer identity and company feedback to A.", "missing": "They do not yet automatically update Suggested company rating / company universe."},
    "I-A": {"status": "PARTIAL", "flow": "Stored company feedback is prepared as company-level evidence for A.", "missing": "Evidence is not yet automatically converted into Suggested A/B/C/Exclude."},
    "H-A": {"status": "PLANNED", "flow": "Hiring outcomes should later inform employer attainability context.", "missing": "Too little outcome data and no A calibration loop yet."},
    "C-G": {"status": "LIVE", "flow": "Role-targeting thesis and calibrated role concepts guide G search vocabulary.", "missing": ""},
    "G-C": {"status": "PARTIAL", "flow": "Country-board G candidates reach the semantic-review layer.", "missing": "Several company/sector staging streams are not yet unified into the same pool."},
    "D-C": {"status": "PARTIAL", "flow": "Remote roles are sourced and available as a separate candidate lane.", "missing": "Not fully integrated into the canonical C review loop."},
    "E-C": {"status": "PARTIAL", "flow": "Project/interim roles are sourced as a separate candidate lane.", "missing": "Sparse pool and not fully integrated into canonical C."},
    "B-C": {"status": "PARTIAL", "flow": "Manual role feedback/context can inform C calibration.", "missing": "The automatic calibration application is not closed-loop yet."},
    "I-C": {"status": "PARTIAL", "flow": "Role feedback and decisions are prepared as C calibration evidence.", "missing": "Batch exists, but does not yet autonomously rewrite the C thesis/semantic store."},
    "H-C": {"status": "PLANNED", "flow": "Attainability evidence should contextualise future semantic/actionability calibration.", "missing": "Not enough outcomes and no live calibration loop."},
    "C-J": {"status": "PARTIAL", "flow": "Semantic judgements feed the final shortlist.", "missing": "Current J still allows explicitly curated Moderate roles; target rule is Strong-only."},
    "COUNTRY-G": {"status": "LIVE", "flow": "Country weights guide sourcing effort across target markets.", "missing": ""},
    "COUNTRY-J": {"status": "PARTIAL", "flow": "Country mix influences J replenishment/diversification.", "missing": "Weights are not yet a joint objective with semantic quality."},
    "QUALITY-J": {"status": "PLANNED", "flow": "Link health and required enrichment should gate roles before J.", "missing": "Live-link validation/quality gate is not built."},
    "B-I": {"status": "LIVE", "flow": "Manual B decisions are surfaced in the unified opportunity/application history.", "missing": ""},
    "J-I": {"status": "LIVE", "flow": "J actions, role/company feedback and comments auto-save into history.", "missing": ""},
    "I-H": {"status": "LIVE", "flow": "Application stages/outcomes are the factual input for H evidence.", "missing": "H inference is intentionally still data-limited."},
}


NODE_COLORS = {
    "green": {"bg": "#F0FDF4", "border": "#22C55E", "text": "#14532D"},
    "blue": {"bg": "#EFF6FF", "border": "#3B82F6", "text": "#1E3A8A"},
    "orange": {"bg": "#FFF7ED", "border": "#F59E0B", "text": "#7C2D12"},
    "purple": {"bg": "#FAF5FF", "border": "#A855F7", "text": "#581C87"},
    "teal": {"bg": "#F0FDFA", "border": "#14B8A6", "text": "#134E4A"},
    "rose": {"bg": "#FFF1F2", "border": "#F43F5E", "text": "#881337"},
    "amber": {"bg": "#FFFBEB", "border": "#D97706", "text": "#78350F"},
    "slate": {"bg": "#F8FAFC", "border": "#94A3B8", "text": "#334155"},
}
EDGE_COLORS = {"LIVE": "#16A34A", "PARTIAL": "#D97706", "PLANNED": "#94A3B8"}


def _style(color: str, width: int = 230, min_height: int = 125) -> dict:
    c = NODE_COLORS[color]
    return {
        "background": c["bg"], "border": f"1.5px solid {c['border']}", "borderRadius": "12px",
        "padding": "12px 14px", "width": f"{width}px", "minHeight": f"{min_height}px",
        "color": c["text"], "fontSize": "12px", "lineHeight": "1.25",
        "boxShadow": "0 3px 12px rgba(15, 23, 42, 0.06)",
    }


def _node(node_id: str, pos: tuple[int, int], content: str, color: str, *, width: int = 230,
          min_height: int = 125, source_position: str = "bottom", target_position: str = "top") -> StreamlitFlowNode:
    return StreamlitFlowNode(
        id=node_id, pos=pos, data={"content": content}, node_type="default",
        source_position=source_position, target_position=target_position,
        draggable=True, selectable=True, connectable=False, deletable=False,
        style=_style(color, width, min_height),
    )


def _edge(edge_id: str, source: str, target: str, label: str, status: str, *, kind: str = "data") -> StreamlitFlowEdge:
    color = EDGE_COLORS[status]
    dashed = kind != "data" or status == "PLANNED"
    style = {"stroke": color, "strokeWidth": 2.4}
    if dashed:
        style["strokeDasharray"] = "7 5"
    return StreamlitFlowEdge(
        id=edge_id, source=source, target=target, edge_type="smoothstep",
        marker_end={"type": "arrowclosed", "color": color},
        animated=status == "LIVE" and kind == "data",
        label=f"{status} · {label}",
        label_style={"fill": color, "fontWeight": 700, "fontSize": 9},
        label_show_bg=True, label_bg_style={"fill": "#FFFFFF", "fillOpacity": 0.94}, style=style,
    )


def _initial_state() -> StreamlitFlowState:
    nodes = [
        _node("A", (70, 40), "### A — Company Intelligence\n🟡 **Core LIVE / learning TODO**\nEmployer universe + priority\n\nRole fit stays separate", "green"),
        _node("B", (345, 40), "### B — Manual Intake\n🟢 **LIVE**\nURL → company/role enrichment\n\nSalary research required", "blue"),
        _node("D", (620, 40), "### D — Remote\n🟢 **LIVE / secondary**\nDaily remote sourcing", "orange"),
        _node("E", (895, 40), "### E — Projects / Interim\n🟡 **LIVE / sparse**\nContract & interim lane", "purple"),
        _node("F", (1170, 40), "### F — People / Network\n⚪ **Ready / inactive**\nConnections → employer access signal", "teal"),
        _node("G", (320, 300), "## G — Aggregated Sourcing Engine\n🟡 **PARTIAL integration**\nCompany + PE + consulting + sectors + boards\n\nDeduplicate → feasibility → candidate pool", "amber", width=800, min_height=150),
        _node("C", (500, 550), "## C — Semantic Fit Review\n🟡 **Core works / integration TODO**\nStrong / Moderate / Weak\n\nCanonical role-fit truth", "green", width=430, min_height=150),
        _node("COUNTRY", (70, 700), "#### Country Targeting\nSoft weights\n\nSearch effort + diversification\nNever a quota", "blue", width=240, min_height=120, source_position="right", target_position="right"),
        _node("J", (500, 785), "## J — Apply Shortlist\n🟢 **LIVE**\nActionable roles + salary + links\n\nApply / Maybe / Skip + feedback", "blue", width=430, min_height=150),
        _node("QUALITY", (1040, 780), "#### Link & Data Quality\n⚪ **NOT BUILT**\nDead-link + enrichment gate", "slate", width=240, min_height=110, source_position="left", target_position="left"),
        _node("I", (390, 1035), "## I — Opportunity History\n🟢 **LIVE**\nDecisions + stages + comments\n\nSingle factual lifecycle store", "rose", width=430, min_height=145),
        _node("H", (920, 1035), "## H — Attainability\n🟡 **Input LIVE / inference early**\nInterview → case → final → offer", "teal", width=360, min_height=145),
    ]

    edges = [
        _edge("A-G", "A", "G", "company universe / priority", "LIVE"),
        _edge("G-A", "G", "A", "new employers", "PLANNED", kind="feedback"),
        _edge("A-C", "A", "C", "company context", "PARTIAL", kind="context"),
        _edge("A-J", "A", "J", "company context", "LIVE", kind="context"),
        _edge("A-F", "A", "F", "canonical companies", "LIVE", kind="context"),
        _edge("F-A", "F", "A", "access signal", "PARTIAL", kind="feedback"),
        _edge("B-A", "B", "A", "manual company signal", "PARTIAL", kind="feedback"),
        _edge("I-A", "I", "A", "historical company feedback", "PARTIAL", kind="feedback"),
        _edge("H-A", "H", "A", "employer outcomes", "PLANNED", kind="feedback"),
        _edge("C-G", "C", "G", "targeting thesis", "LIVE", kind="context"),
        _edge("G-C", "G", "C", "candidate pool", "PARTIAL"),
        _edge("D-C", "D", "C", "remote candidates", "PARTIAL"),
        _edge("E-C", "E", "C", "project candidates", "PARTIAL"),
        _edge("B-C", "B", "C", "manual role signal", "PARTIAL", kind="feedback"),
        _edge("I-C", "I", "C", "role feedback", "PARTIAL", kind="feedback"),
        _edge("H-C", "H", "C", "attainability context", "PLANNED", kind="feedback"),
        _edge("C-J", "C", "J", "semantic fit", "PARTIAL"),
        _edge("COUNTRY-G", "COUNTRY", "G", "search weights", "LIVE", kind="context"),
        _edge("COUNTRY-J", "COUNTRY", "J", "diversification", "PARTIAL", kind="context"),
        _edge("QUALITY-J", "QUALITY", "J", "quality gate", "PLANNED"),
        _edge("B-I", "B", "I", "manual opportunity", "LIVE"),
        _edge("J-I", "J", "I", "decision + feedback", "LIVE"),
        _edge("I-H", "I", "H", "stages + outcomes", "LIVE"),
    ]
    return StreamlitFlowState(nodes, edges)


def _reset_flow() -> None:
    st.session_state[FLOW_STATE_KEY] = _initial_state()


def _render_detail(selected_id: str | None) -> None:
    edge_info = EDGE_DETAILS.get(selected_id or "")
    if edge_info:
        st.markdown(f"### Connection {selected_id}")
        status = edge_info["status"]
        st.markdown(f"**{status}**")
        st.markdown(edge_info["flow"])
        if edge_info["missing"]:
            st.markdown(f"**Missing:** {edge_info['missing']}")
        return

    info = WORKSTREAM_DETAILS.get(selected_id or "") or SUPPORT_DETAILS.get(selected_id or "")
    if info:
        st.markdown(f"### {info['title']}")
        st.caption(info["status"])
        st.markdown(info["purpose"])
        st.markdown(f"**Inputs**  \n{info['inputs']}")
        st.markdown(f"**Outputs**  \n{info['outputs']}")
        st.markdown(f"**Outstanding**  \n{info['outstanding']}")
    else:
        st.info("Click a node or connection to inspect what it does and whether it is actually implemented.")


def render_system_flow() -> None:
    st.markdown('<div class="eyebrow">System architecture</div>', unsafe_allow_html=True)
    st.title("A–J System Flow")
    st.caption("Node = workstream. Connection colour = implementation health. Click either for details.")

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
            "professional_dashboard_system_flow_v2",
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
            st.markdown("#### Connection health")
            st.markdown(
                "🟢 **LIVE** — implemented and carrying the intended data/signals  \n"
                "🟠 **PARTIAL** — some plumbing exists, but target flow is incomplete  \n"
                "⚪ **PLANNED** — shown in target architecture, not implemented yet"
            )
            st.caption("Dashed line = context/feedback or planned relation. Solid line = direct data/opportunity flow.")
