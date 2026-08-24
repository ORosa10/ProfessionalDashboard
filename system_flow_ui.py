from __future__ import annotations

import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState


FLOW_STATE_KEY = "professional_dashboard_system_flow_state_v1"


WORKSTREAM_DETAILS = {
    "A": {
        "title": "A — Company Relevance",
        "status": "🟡 Mature / needs smarter rating loop",
        "purpose": "Maintain the company universe and a live employer prior. Company attractiveness stays separate from role fit, but historical role and outcome evidence should inform a suggested company rating.",
        "inputs": "Explicit company ratings; company feedback from B/J/I; repeated role quality; later H outcomes.",
        "outputs": "Company context and suggested company priority for G/C/J.",
        "outstanding": "Add Suggested A/B/C/Exclude from historical evidence instead of leaving every new company Unrated forever.",
    },
    "B": {
        "title": "B — Manual Opportunity Intake",
        "status": "🟢 Working",
        "purpose": "Capture a role you found yourself and enrich it once, without forcing a duplicate decision in J.",
        "inputs": "LinkedIn and/or company job URL + optional comment.",
        "outputs": "Enriched opportunity → I; company signal → A; role signal → C.",
        "outstanding": "Every new enrichment must include role/company context + researched market salary + explicit salary expectation.",
    },
    "C": {
        "title": "C — Semantic Fit",
        "status": "🟡 Calibrated / canonical store needs cleanup",
        "purpose": "Judge actual responsibilities against the targeting thesis: Strong / Moderate / Weak. This is the semantic truth layer, not a keyword score.",
        "inputs": "Candidate roles from G/D/E; company context from A; historical feedback from I/H; manual-role evidence from B.",
        "outputs": "Canonical semantic judgement; Strong actionable roles → J.",
        "outstanding": "Consolidate current curated J judgements back into canonical semantic_fit data and stop parallel truths.",
    },
    "D": {
        "title": "D — Remote",
        "status": "🟢 Running / secondary",
        "purpose": "Automated remote-role exploration, kept secondary to the core permanent-role pipeline.",
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
        "purpose": "Match LinkedIn connections to the company universe and provide an access signal without overriding intrinsic fit.",
        "inputs": "LinkedIn Connections CSV export.",
        "outputs": "Access/network context for A and opportunity prioritisation.",
        "outstanding": "No data loaded yet; activate when networking becomes useful.",
    },
    "G": {
        "title": "G — Sourcing Engine",
        "status": "🟡 Running sources / integration incomplete",
        "purpose": "Aggregate company, PE, consulting, sector and country-board sourcing into one broad actionable candidate pool across target markets.",
        "inputs": "A company universe + C targeting thesis + country weights + configured boards/company career sites.",
        "outputs": "Deduplicated, language-feasible candidate pool → C.",
        "outstanding": "Unify the currently separate staging branches and repair/verify the daily country-board run so all sourcing can reach C/J.",
    },
    "H": {
        "title": "H — Attainability",
        "status": "🟡 Early / data-limited",
        "purpose": "Infer what you can realistically land from actual application outcomes, separately from whether a role is attractive.",
        "inputs": "Application stages and outcomes from I.",
        "outputs": "Attainability evidence by role/company/market → future A/C calibration.",
        "outstanding": "Accumulate enough real interviews/rejections/cases/offers before making model-like inferences.",
    },
    "I": {
        "title": "I — Opportunity & Application History",
        "status": "🟢 Working",
        "purpose": "Single factual memory of decisions and application lifecycle for both manual and sourced opportunities.",
        "inputs": "B decisions; J Apply/Maybe/Skip; later application-stage updates.",
        "outputs": "Feedback batch → A/C; outcomes → H.",
        "outstanding": "Keep stages current; J feedback now auto-saves successfully.",
    },
    "J": {
        "title": "J — Apply Shortlist",
        "status": "🟢 Working / selection logic still evolving",
        "purpose": "Final working queue of genuinely actionable roles, with salary context, links and feedback controls.",
        "inputs": "Strong semantic roles from C + country guidance + company/access context + salary research.",
        "outputs": "Apply/Maybe/Skip + company/role feedback → I.",
        "outstanding": "Move to Strong-only, integrate country weights jointly with quality, and add link-health checks before display.",
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
    "CONTEXT": {
        "title": "Historical Context",
        "status": "Feedback memory",
        "purpose": "Past decisions, semantic judgements, comments and outcomes provide context for future company and role decisions.",
        "inputs": "I + H + C history.",
        "outputs": "Feedback context → A/C.",
        "outstanding": "Keep explicit company and role signals separate to avoid learning the wrong lesson.",
    },
    "QUALITY": {
        "title": "Link & Data Quality",
        "status": "Needs work",
        "purpose": "Prevent dead links or missing salary/context from reaching the final shortlist unnoticed.",
        "inputs": "Job URL, salary enrichment, required fields.",
        "outputs": "Quality flags on J candidates.",
        "outstanding": "Add live-link check and salary-present check before J.",
    },
}


COLORS = {
    "green": {"bg": "#F0FDF4", "border": "#22C55E", "text": "#14532D"},
    "blue": {"bg": "#EFF6FF", "border": "#3B82F6", "text": "#1E3A8A"},
    "orange": {"bg": "#FFF7ED", "border": "#F59E0B", "text": "#7C2D12"},
    "purple": {"bg": "#FAF5FF", "border": "#A855F7", "text": "#581C87"},
    "teal": {"bg": "#F0FDFA", "border": "#14B8A6", "text": "#134E4A"},
    "rose": {"bg": "#FFF1F2", "border": "#F43F5E", "text": "#881337"},
    "amber": {"bg": "#FFFBEB", "border": "#D97706", "text": "#78350F"},
    "slate": {"bg": "#F8FAFC", "border": "#94A3B8", "text": "#334155"},
}


def _style(color: str, width: int = 230, min_height: int = 125) -> dict:
    c = COLORS[color]
    return {
        "background": c["bg"],
        "border": f"1.5px solid {c['border']}",
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
    content: str,
    color: str,
    *,
    width: int = 230,
    min_height: int = 125,
    source_position: str = "bottom",
    target_position: str = "top",
) -> StreamlitFlowNode:
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
        style=_style(color, width, min_height),
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    label: str = "",
    color: str = "#64748B",
    dashed: bool = False,
    animated: bool = False,
) -> StreamlitFlowEdge:
    style = {"stroke": color, "strokeWidth": 2}
    if dashed:
        style["strokeDasharray"] = "6 5"
    return StreamlitFlowEdge(
        id=edge_id,
        source=source,
        target=target,
        edge_type="smoothstep",
        marker_end={"type": "arrowclosed", "color": color},
        animated=animated,
        label=label,
        label_style={"fill": color, "fontWeight": 600, "fontSize": 10},
        label_show_bg=True,
        label_bg_style={"fill": "#FFFFFF", "fillOpacity": 0.92},
        style=style,
    )


def _initial_state() -> StreamlitFlowState:
    nodes = [
        _node("A", (80, 50), "### A — Company Relevance\n🟡 **Mature**\nCompany universe + live employer prior\n\nHistorical signals should suggest ratings", "green"),
        _node("B", (350, 50), "### B — Manual Intake\n🟢 **Working**\nAdd URL → enrich company + role\n\n**Salary research always added**", "blue"),
        _node("D", (620, 50), "### D — Remote\n🟢 **Running**\nDaily remote sourcing\n\nSecondary opportunity lane", "orange"),
        _node("E", (890, 50), "### E — Projects / Interim\n🟡 **Sparse**\nContract / interim sourcing\n\nSeparate project lane", "purple"),
        _node("F", (1160, 50), "### F — People / Network\n⚪ **Deferred**\nLinkedIn connections → company match\n\nAccess signal only", "teal"),
        _node("G", (330, 300), "## G — Aggregated Sourcing Engine\n🟡 **Sources run; integration incomplete**\nCompany + PE + consulting + sectors + country boards\n\nDeduplicate → language feasibility → candidate pool", "amber", width=790, min_height=150),
        _node("CONTEXT", (40, 330), "#### Historical Context\nI + H + C\n\nPast decisions, comments, semantic history and outcomes", "slate", width=230, min_height=120, source_position="right", target_position="right"),
        _node("C", (500, 540), "## C — Semantic Fit Review\n🟡 **Calibrated**\nHuman-in-the-loop semantic judgement\n\n**Strong / Moderate / Weak**\nCanonical role-fit truth", "green", width=430, min_height=155),
        _node("COUNTRY", (70, 720), "#### Country Targeting\nSoft target weights\n\nGuides search effort + diversification\n**Never a quota**", "blue", width=240, min_height=125, source_position="right", target_position="right"),
        _node("J", (500, 760), "## J — Apply Shortlist\n🟢 **Working**\nStrong actionable roles + salary + links\n\nApply / Maybe / Skip + feedback", "blue", width=430, min_height=150),
        _node("QUALITY", (1030, 750), "#### Link & Data Quality\nDead-link check\nSalary present?\nRequired context present?", "slate", width=240, min_height=120, source_position="left", target_position="left"),
        _node("I", (390, 1010), "## I — Opportunity History\n🟢 **Working**\nDecisions + application stages + comments\n\nSingle factual lifecycle store", "rose", width=430, min_height=145),
        _node("H", (920, 1010), "## H — Attainability\n🟡 **Data-limited**\nInterview / case / final / offer evidence\n\nFeeds future calibration", "teal", width=360, min_height=145),
    ]

    edges = [
        _edge("A-G", "A", "G", label="company universe", animated=True),
        _edge("C-G", "C", "G", label="targeting thesis", color="#16A34A", dashed=True),
        _edge("G-C", "G", "C", label="candidate pool", animated=True),
        _edge("D-C", "D", "C", label="remote candidates"),
        _edge("E-C", "E", "C", label="project candidates"),
        _edge("C-J", "C", "J", label="Strong only", color="#2563EB", animated=True),
        _edge("COUNTRY-G", "COUNTRY", "G", label="search weights", color="#2563EB", dashed=True),
        _edge("COUNTRY-J", "COUNTRY", "J", label="diversification", color="#2563EB", dashed=True),
        _edge("QUALITY-J", "QUALITY", "J", label="quality gate", color="#64748B", dashed=True),
        _edge("J-I", "J", "I", label="decision + feedback", color="#E11D48", animated=True),
        _edge("B-I", "B", "I", label="manual opportunity", color="#2563EB", animated=True),
        _edge("B-A", "B", "A", label="company signal", color="#E11D48", dashed=True),
        _edge("B-C", "B", "C", label="role signal", color="#E11D48", dashed=True),
        _edge("I-H", "I", "H", label="stages + outcomes", color="#0F766E", animated=True),
        _edge("H-C", "H", "C", label="attainability context", color="#7C3AED", dashed=True),
        _edge("H-A", "H", "A", label="employer outcome context", color="#E11D48", dashed=True),
        _edge("I-CONTEXT", "I", "CONTEXT", label="history", color="#E11D48", dashed=True),
        _edge("CONTEXT-A", "CONTEXT", "A", label="rating context", color="#E11D48", dashed=True),
        _edge("CONTEXT-C", "CONTEXT", "C", label="semantic context", color="#7C3AED", dashed=True),
        _edge("F-A", "F", "A", label="access signal", color="#0F766E", dashed=True),
    ]
    return StreamlitFlowState(nodes, edges)


def _reset_flow() -> None:
    st.session_state[FLOW_STATE_KEY] = _initial_state()


def render_system_flow() -> None:
    st.markdown('<div class="eyebrow">System architecture</div>', unsafe_allow_html=True)
    st.title("A–J System Flow")
    st.caption(
        "Interactive map of the opportunity engine. Drag nodes, zoom/pan the canvas, "
        "and click a workstream to inspect what it does and what is still outstanding."
    )

    top_left, top_right = st.columns([4, 1])
    with top_right:
        if st.button("Reset layout", use_container_width=True):
            _reset_flow()
            st.rerun()

    if FLOW_STATE_KEY not in st.session_state:
        st.session_state[FLOW_STATE_KEY] = _initial_state()

    canvas, detail = st.columns([4.6, 1.4], gap="large")
    with canvas:
        st.session_state[FLOW_STATE_KEY] = streamlit_flow(
            "professional_dashboard_system_flow",
            st.session_state[FLOW_STATE_KEY],
            fit_view=True,
            height=980,
            show_controls=True,
            show_minimap=True,
            hide_watermark=True,
            allow_new_edges=False,
            enable_node_menu=False,
            enable_edge_menu=False,
            enable_pane_menu=False,
            get_node_on_click=True,
            get_edge_on_click=False,
            min_zoom=0.2,
        )

    selected_id = getattr(st.session_state[FLOW_STATE_KEY], "selected_id", None)
    info = WORKSTREAM_DETAILS.get(selected_id) or SUPPORT_DETAILS.get(selected_id)

    with detail:
        st.subheader("Selected node")
        if info:
            st.markdown(f"### {info['title']}")
            st.caption(info["status"])
            st.markdown(info["purpose"])
            st.markdown(f"**Inputs**  \n{info['inputs']}")
            st.markdown(f"**Outputs**  \n{info['outputs']}")
            st.markdown(f"**Outstanding**  \n{info['outstanding']}")
        else:
            st.info("Click any A–J node to see its purpose, inputs, outputs and outstanding work.")

        st.divider()
        st.markdown("#### Legend")
        st.markdown(
            "**Solid arrow** — data / opportunity flow  \n"
            "**Dashed blue** — country guidance  \n"
            "**Dashed pink/purple** — feedback / context  \n"
            "**🟢** working  ·  **🟡** needs work  ·  **⚪** deferred"
        )

        st.divider()
        st.markdown("#### Core loop")
        st.code("A + C → G → C → J → I → H\nB → enrichment → I\nI/H → feedback → A + C")
        st.caption("B does not need to re-enter J: it is already a manually selected opportunity.")
