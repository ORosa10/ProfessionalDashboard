from __future__ import annotations

import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState


# v3 intentionally resets old browser layout after the agreed C-flow cleanup.
FLOW_STATE_KEY = "professional_dashboard_system_flow_state_v3"


WORKSTREAM_DETAILS = {
    "A": {
        "title": "A — Company Intelligence / Relevance",
        "status": "🟡 Core works; learning loop incomplete",
        "purpose": (
            "Maintain the employer universe and company priority. A answers whether an employer is worth "
            "systematically following; it does NOT decide whether a specific role is a good fit."
        ),
        "inputs": (
            "User → explicit A/B/C/Exclude + notes; B → newly discovered employer identity/context; "
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
        "purpose": "Capture a role found manually, treat it as Interested, enrich it and store it without forcing a duplicate decision in J.",
        "inputs": "LinkedIn and/or company job URL + optional comment.",
        "outputs": (
            "Interested opportunity → I immediately. Employer identity/context may also surface to A. "
            "Role/company preference learning is routed through I, not directly into C/A."
        ),
        "outstanding": "Keep zero-cost salary research reliable; low-confidence cases can be reviewed in ChatGPT.",
    },
    "C": {
        "title": "C — Semantic Role Fit",
        "status": "🟡 Core judgement works; canonical/integration cleanup needed",
        "purpose": (
            "Answer one question only: is the actual content of this specific job something the user wants to do? "
            "Judge responsibilities, requirements and seniority as Strong / Moderate / Weak."
        ),
        "inputs": (
            "Candidate flow: G/D/E → concrete new roles to classify. Context: A → company identity/rating only, never a hard gate. "
            "Learning flow: I → historical role feedback from both B and J. Explicit role thesis/preferences define the calibration basis. "
            "H, salary, geography, language and link health do NOT determine semantic fit."
        ),
        "outputs": (
            "C → J: semantic judgement for already-discovered current roles. "
            "C → G: learned role concepts/search intelligence for future sourcing."
        ),
        "outstanding": (
            "Make semantic_fit.csv the single canonical truth, backfill curated J judgements, integrate every G/D/E candidate lane, "
            "and close the I → C calibration loop without mixing attainability or actionability into fit."
        ),
    },
    "D": {
        "title": "D — Remote",
        "status": "🟢 Running / secondary",
        "purpose": "Automated remote-role exploration, secondary to the core permanent-role pipeline.",
        "inputs": "Public remote job boards.",
        "outputs": "Concrete remote candidate roles → C for semantic classification.",
        "outstanding": "Tighten Europe/employability filter so US-only remote roles do not create noise.",
    },
    "E": {
        "title": "E — Projects / Interim",
        "status": "🟡 Running / sparse",
        "purpose": "Source contract, interim, freelance and project finance work as a separate lane.",
        "inputs": "Remote/project boards; later tender channels if useful.",
        "outputs": "Concrete project/interim candidates → C for semantic classification.",
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
        "inputs": "A company universe + C role/search intelligence + country weights + configured boards/career sites.",
        "outputs": "Deduplicated candidate roles → C; newly discovered employers → A (target state).",
        "outstanding": "Unify separate staging branches and repair/verify the daily country-board run so all sourcing can reach C/J.",
    },
    "H": {
        "title": "H — Attainability",
        "status": "🟡 Early / data-limited",
        "purpose": "Infer realistic chance of landing similar roles from actual application outcomes, separately from preference fit.",
        "inputs": "Application stages and outcomes from I.",
        "outputs": "Attainability evidence → future employer/opportunity context; it does not change C semantic fit.",
        "outstanding": "Accumulate enough interviews/rejections/cases/offers before making model-like inferences.",
    },
    "I": {
        "title": "I — Opportunity & Application History",
        "status": "🟢 Working",
        "purpose": "Single factual memory and central feedback hub for manual and sourced opportunities.",
        "inputs": "B Interested opportunities; J Apply/Maybe/Skip + role/company feedback; later application-stage updates.",
        "outputs": "Company feedback → A; role-content feedback → C; application stages/outcomes → H.",
        "outstanding": "Close the A/C learning loops while keeping factual history separate from inferred models.",
    },
    "J": {
        "title": "J — Apply Shortlist",
        "status": "🟢 Working; selection logic still evolving",
        "purpose": "Final working queue of genuinely actionable roles, with salary context, links and feedback controls.",
        "inputs": "Current-role semantic judgement from C + company context from A + country/actionability guidance + salary research.",
        "outputs": "Apply/Maybe/Skip + company/role feedback → I. I then routes preference learning to A/C and outcomes to H.",
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
    "A-C": {"status": "PARTIAL", "flow": "Company identity/rating/context accompanies a role into semantic review as context only; it must not determine Strong/Moderate/Weak.", "missing": "Canonical C integration is not yet fully consolidated."},
    "A-J": {"status": "LIVE", "flow": "J can display/use company rating/context when comparing otherwise good roles.", "missing": ""},
    "A-F": {"status": "LIVE", "flow": "Canonical company IDs/aliases are used to match uploaded network contacts.", "missing": "F currently has no uploaded connection data."},
    "F-A": {"status": "PARTIAL", "flow": "Matched contacts can provide an access signal for companies.", "missing": "No network data loaded, so the signal is operationally inactive."},
    "B-A": {"status": "PARTIAL", "flow": "A manually submitted role can expose a previously unknown employer identity/context to A.", "missing": "No systematic B → A new-employer ingestion yet; preference feedback itself goes B → I → A."},
    "I-A": {"status": "PARTIAL", "flow": "Company feedback from both B/J history is prepared as company-level evidence for A.", "missing": "Evidence is not yet automatically converted into Suggested A/B/C/Exclude."},
    "H-A": {"status": "PLANNED", "flow": "Hiring outcomes may later inform employer attainability context in A without changing intrinsic company preference.", "missing": "Too little outcome data and no A calibration loop yet."},
    "C-G": {"status": "PARTIAL", "flow": "C role thesis/concepts guide future G search vocabulary and search effort.", "missing": "Current targeting concepts are used, but I-driven C learning does not yet automatically update G search intelligence."},
    "G-C": {"status": "PARTIAL", "flow": "G sends concrete newly discovered candidate roles to C for Strong/Moderate/Weak classification.", "missing": "Country-board roles reach C, but several company/sector staging streams are not yet unified into the same candidate flow."},
    "D-C": {"status": "PARTIAL", "flow": "D sends concrete remote candidate roles to C for the same semantic classification.", "missing": "Remote staging is not fully integrated into the canonical C queue."},
    "E-C": {"status": "PARTIAL", "flow": "E sends concrete project/interim candidate roles to C for the same semantic classification.", "missing": "Project pool is sparse and not fully integrated into the canonical C queue."},
    "I-C": {"status": "PARTIAL", "flow": "I sends historical role-content preference evidence from both B and J into C calibration; this is learning feedback, not a new candidate-role flow.", "missing": "Feedback batch/evidence exists, but does not yet close the loop into the canonical C thesis/store automatically."},
    "C-J": {"status": "PARTIAL", "flow": "For an already-discovered current role, C sends its semantic judgement directly toward J; it does not need to go back through G first.", "missing": "J still contains parallel curated semantic truth and can include curated Moderate roles; target is canonical C + actionability + Strong-only."},
    "COUNTRY-G": {"status": "LIVE", "flow": "Country weights guide sourcing effort across target markets.", "missing": ""},
    "COUNTRY-J": {"status": "PARTIAL", "flow": "Country mix influences J replenishment/diversification after semantic quality is known.", "missing": "Weights are not yet a joint objective with semantic quality."},
    "QUALITY-J": {"status": "PLANNED", "flow": "Link health, language/actionability and required enrichment should gate roles before J.", "missing": "Unified actionability/link validation gate is not built."},
    "B-I": {"status": "LIVE", "flow": "Every manually added B opportunity is Interested and enters the unified opportunity/application history immediately.", "missing": ""},
    "J-I": {"status": "LIVE", "flow": "J actions, role/company feedback and comments auto-save into I; I is the feedback hub for downstream learning.", "missing": ""},
    "I-H": {"status": "LIVE", "flow": "Application stages/outcomes are the factual input for H attainability evidence.", "missing": "H inference is intentionally still data-limited."},
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
        _node("B", (345, 40), "### B — Manual Intake\n🟢 **LIVE**\nManual role = Interested → I\n\nZero-cost salary research", "blue"),
        _node("D", (620, 40), "### D — Remote\n🟢 **LIVE / secondary**\nRemote candidate lane → C", "orange"),
        _node("E", (895, 40), "### E — Projects / Interim\n🟡 **LIVE / sparse**\nProject candidate lane → C", "purple"),
        _node("F", (1170, 40), "### F — People / Network\n⚪ **Ready / inactive**\nConnections → employer access signal", "teal"),
        _node("G", (320, 300), "## G — Aggregated Sourcing Engine\n🟡 **PARTIAL integration**\nCompany + PE + consulting + sectors + boards\n\nNew candidate roles → C", "amber", width=800, min_height=150),
        _node("C", (500, 550), "## C — Semantic Role Fit\n🟡 **Core works / integration TODO**\nJob content only: Strong / Moderate / Weak\n\nCandidate flow ≠ learning feedback", "green", width=430, min_height=160),
        _node("COUNTRY", (70, 700), "#### Country Targeting\nSoft weights\n\nSearch effort + diversification\nNever semantic fit", "blue", width=240, min_height=120, source_position="right", target_position="right"),
        _node("J", (500, 785), "## J — Apply Shortlist\n🟢 **LIVE**\nActionable roles + salary + links\n\nFeedback → I, not directly C", "blue", width=430, min_height=150),
        _node("QUALITY", (1040, 780), "#### Actionability / Quality\n⚪ **NOT BUILT**\nLanguage + geo + link + enrichment gate", "slate", width=250, min_height=120, source_position="left", target_position="left"),
        _node("I", (390, 1035), "## I — History + Feedback Hub\n🟢 **LIVE store**\nB + J decisions / feedback / stages\n\nRole feedback → C · outcomes → H", "rose", width=440, min_height=155),
        _node("H", (920, 1035), "## H — Attainability\n🟡 **Input LIVE / inference early**\nInterview → case → final → offer\n\nDoes NOT change C fit", "teal", width=360, min_height=150),
    ]

    edges = [
        _edge("A-G", "A", "G", "company universe / priority", "LIVE"),
        _edge("G-A", "G", "A", "new employers", "PLANNED", kind="feedback"),
        _edge("A-C", "A", "C", "company context only", "PARTIAL", kind="context"),
        _edge("A-J", "A", "J", "company context", "LIVE", kind="context"),
        _edge("A-F", "A", "F", "canonical companies", "LIVE", kind="context"),
        _edge("F-A", "F", "A", "access signal", "PARTIAL", kind="feedback"),
        _edge("B-A", "B", "A", "new employer identity", "PARTIAL", kind="context"),
        _edge("I-A", "I", "A", "company feedback", "PARTIAL", kind="feedback"),
        _edge("H-A", "H", "A", "employer outcomes", "PLANNED", kind="feedback"),
        _edge("C-G", "C", "G", "future search intelligence", "PARTIAL", kind="feedback"),
        _edge("G-C", "G", "C", "candidate roles", "PARTIAL"),
        _edge("D-C", "D", "C", "remote candidate roles", "PARTIAL"),
        _edge("E-C", "E", "C", "project candidate roles", "PARTIAL"),
        _edge("I-C", "I", "C", "role preference learning", "PARTIAL", kind="feedback"),
        _edge("C-J", "C", "J", "current-role semantic fit", "PARTIAL"),
        _edge("COUNTRY-G", "COUNTRY", "G", "search weights", "LIVE", kind="context"),
        _edge("COUNTRY-J", "COUNTRY", "J", "diversification", "PARTIAL", kind="context"),
        _edge("QUALITY-J", "QUALITY", "J", "actionability gate", "PLANNED"),
        _edge("B-I", "B", "I", "Interested opportunity", "LIVE"),
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
            "professional_dashboard_system_flow_v3",
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
            st.caption("Solid = concrete candidate/data flow. Dashed = context, learning feedback or planned relation.")