from __future__ import annotations

import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState


# v5 resets the browser layout after the agreed H attainability-flow cleanup.
FLOW_STATE_KEY = "professional_dashboard_system_flow_state_v5"


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
            "G → newly discovered employers; I → historical company preference feedback; "
            "H → employer attainability context from actual hiring outcomes; F → optional network/access signal."
        ),
        "outputs": (
            "A → G: company universe, priority, career URLs and category for sourcing. "
            "A → C/J: company rating/context only (not a hard role gate). "
            "A → F: canonical companies/aliases for optional contact matching."
        ),
        "outstanding": (
            "Add Suggested A/B/C/Exclude from historical company evidence and ingest newly discovered employers "
            "from G/B without overwriting explicit user ratings; later display H attainability separately from A preference."
        ),
    },
    "B": {
        "title": "B — Manual Opportunity Intake",
        "status": "🟢 Core / working",
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
            "Core candidate flow: G → concrete new roles to classify. Optional candidate lanes: D/E → remote or project roles. "
            "Context: A → company identity/rating only. Learning flow: I → historical role feedback from both B and J. "
            "H may add separate role-type/seniority attainability context, but it must never change Strong/Moderate/Weak. "
            "Salary, geography, language and link health do NOT determine semantic fit."
        ),
        "outputs": (
            "C → J: semantic judgement for already-discovered current roles. "
            "C → G: learned role concepts/search intelligence for future sourcing."
        ),
        "outstanding": (
            "Make semantic_fit.csv the single canonical truth, backfill curated J judgements, integrate the core G candidate flow, "
            "and close the I → C calibration loop. D/E integration is secondary."
        ),
    },
    "D": {
        "title": "D — Remote",
        "status": "⚪ Secondary / partially built",
        "purpose": "Optional remote-role discovery lane outside the core permanent-role engine.",
        "inputs": "Public remote job boards + C targeting concepts.",
        "outputs": "Optional remote candidate roles → C for the same semantic classification as core roles.",
        "outstanding": "Revisit later: tighten Europe/employability logic and integrate remote staging into canonical C only if this lane becomes useful.",
    },
    "E": {
        "title": "E — Projects / Interim",
        "status": "⚪ Secondary / sparse",
        "purpose": "Optional contract, interim, freelance and project-finance sourcing lane outside the core engine.",
        "inputs": "Remote/project boards; later tender channels if useful.",
        "outputs": "Optional project/interim candidates → C for semantic classification.",
        "outstanding": "Revisit later. Current result pool is sparse; do not spend core-development effort here yet.",
    },
    "F": {
        "title": "F — People / Network",
        "status": "⚪ Secondary / deferred",
        "purpose": "Optional access layer: match contacts to canonical employers and provide a network/referral signal without changing intrinsic fit.",
        "inputs": "LinkedIn Connections CSV + canonical companies from A.",
        "outputs": "Optional access/network context → A and later opportunity prioritisation.",
        "outstanding": "Deferred until networking becomes an active part of the search; no connection data is loaded today.",
    },
    "G": {
        "title": "G — Sourcing Engine",
        "status": "🟡 Core; sources run but integration incomplete",
        "purpose": "Aggregate company, PE, consulting, sector and country-board sourcing into one broad candidate pool.",
        "inputs": (
            "A company universe + C role/search intelligence + country weights + configured boards/career sites. "
            "Later, H may softly reweight search effort toward segments with better empirical attainability while preserving aspirational exploration."
        ),
        "outputs": "Deduplicated candidate roles → C; newly discovered employers → A (target state).",
        "outstanding": "Unify separate staging branches and repair/verify the daily country-board run so all core sourcing can reach C/J.",
    },
    "H": {
        "title": "H — Attainability",
        "status": "🟡 Core / evidence input works; inference is data-limited",
        "purpose": (
            "Learn how realistic it is to land similar roles from actual application outcomes. "
            "Attainability is separate from company preference (A) and semantic role fit (C)."
        ),
        "inputs": (
            "I → actual application lifecycle and outcomes only: Applied, rejected pre-screen, interview, case, final, offer, withdrawal, "
            "plus the role/company/seniority/geography context needed to group comparable outcomes."
        ),
        "outputs": (
            "H → A: employer/employer-type attainability context without changing A/B/C/Exclude preference. "
            "H → C: role-family/seniority attainability context without changing Strong/Moderate/Weak. "
            "H → G: soft search-effort signal, never a hard exclusion. "
            "H → J: soft application priority/context among otherwise actionable roles."
        ),
        "outstanding": (
            "Accumulate enough interviews/rejections/cases/finals/offers, add confidence/sample-size handling, then build grouped attainability estimates "
            "and expose them separately in A/C/J plus a soft sourcing-weight signal to G."
        ),
    },
    "I": {
        "title": "I — Opportunity & Application History",
        "status": "🟢 Core / working",
        "purpose": "Single factual memory and central feedback hub for manual and sourced opportunities.",
        "inputs": "B Interested opportunities; J Apply/Maybe/Skip + role/company feedback; later application-stage updates.",
        "outputs": "Company preference feedback → A; role-content feedback → C; actual application stages/outcomes → H.",
        "outstanding": "Close the A/C learning loops while keeping factual history separate from inferred models.",
    },
    "J": {
        "title": "J — Apply Shortlist",
        "status": "🟢 Core / working; selection logic still evolving",
        "purpose": "Final working queue of genuinely actionable roles, with salary context, links and feedback controls.",
        "inputs": (
            "Current-role semantic judgement from C + company context from A + country/actionability guidance + salary research. "
            "Later H adds separate empirical attainability context/priority; low H must not automatically remove a Strong role."
        ),
        "outputs": "Apply/Maybe/Skip + company/role feedback → I. I then routes preference learning to A/C and actual outcomes to H.",
        "outstanding": "Move to Strong-only, integrate country weights jointly with quality, add link-health checks and later show H attainability context.",
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
    "A-F": {"status": "LIVE", "flow": "Canonical company IDs/aliases are available for the optional F network-matching lane.", "missing": "F is deferred and currently has no uploaded connection data."},
    "F-A": {"status": "PARTIAL", "flow": "If activated, matched contacts can provide an optional employer access signal.", "missing": "Secondary/deferred lane; no network data loaded."},
    "B-A": {"status": "PARTIAL", "flow": "A manually submitted role can expose a previously unknown employer identity/context to A.", "missing": "No systematic B → A new-employer ingestion yet; preference feedback itself goes B → I → A."},
    "I-A": {"status": "PARTIAL", "flow": "Company preference feedback from both B/J history is prepared as company-level evidence for A.", "missing": "Evidence is not yet automatically converted into Suggested A/B/C/Exclude."},
    "H-A": {"status": "PLANNED", "flow": "H should add empirical employer/employer-type attainability context to A while leaving intrinsic company preference unchanged.", "missing": "No grouped H model/context field yet; outcome sample is still small."},
    "C-G": {"status": "PARTIAL", "flow": "C role thesis/concepts guide future G search vocabulary and search effort.", "missing": "Current targeting concepts are used, but I-driven C learning does not yet automatically update G search intelligence."},
    "G-C": {"status": "PARTIAL", "flow": "G sends concrete newly discovered candidate roles to C for Strong/Moderate/Weak classification.", "missing": "Country-board roles reach C, but several company/sector staging streams are not yet unified into the same candidate flow."},
    "D-C": {"status": "PARTIAL", "flow": "Optional D remote roles can be sent to C for the same semantic classification.", "missing": "Secondary lane; remote staging is not fully integrated into canonical C and is not a current core priority."},
    "E-C": {"status": "PARTIAL", "flow": "Optional E project/interim roles can be sent to C for the same semantic classification.", "missing": "Secondary lane; pool is sparse and not fully integrated into canonical C."},
    "I-C": {"status": "PARTIAL", "flow": "I sends historical role-content preference evidence from both B and J into C calibration; this is learning feedback, not a new candidate-role flow.", "missing": "Feedback batch/evidence exists, but does not yet close the loop into the canonical C thesis/store automatically."},
    "H-C": {"status": "PLANNED", "flow": "H should add empirical attainability context for comparable role families/seniority bands without changing the C semantic-fit rating.", "missing": "No grouped H model/context field yet; outcome sample is still small."},
    "C-J": {"status": "PARTIAL", "flow": "For an already-discovered current role, C sends its semantic judgement directly toward J; it does not need to go back through G first.", "missing": "J still contains parallel curated semantic truth and can include curated Moderate roles; target is canonical C + actionability + Strong-only."},
    "H-G": {"status": "PLANNED", "flow": "H may softly reweight future G sourcing toward empirically attainable segments while retaining exploration and aspirational roles.", "missing": "No attainability model or soft sourcing-weight integration yet."},
    "H-J": {"status": "PLANNED", "flow": "H should provide a separate attainability/confidence signal for J prioritisation; low attainability is context, not an automatic exclusion.", "missing": "No H score/context is currently displayed or used in J."},
    "COUNTRY-G": {"status": "LIVE", "flow": "Country weights guide sourcing effort across target markets.", "missing": ""},
    "COUNTRY-J": {"status": "PARTIAL", "flow": "Country mix influences J replenishment/diversification after semantic quality is known.", "missing": "Weights are not yet a joint objective with semantic quality."},
    "QUALITY-J": {"status": "PLANNED", "flow": "Link health, language/actionability and required enrichment should gate roles before J.", "missing": "Unified actionability/link validation gate is not built."},
    "B-I": {"status": "LIVE", "flow": "Every manually added B opportunity is Interested and enters the unified opportunity/application history immediately.", "missing": ""},
    "J-I": {"status": "LIVE", "flow": "J actions, role/company feedback and comments auto-save into I; I is the feedback hub for downstream learning.", "missing": ""},
    "I-H": {"status": "LIVE", "flow": "Actual application stages/outcomes in I are the factual input for H evidence; preference actions alone are not attainability evidence.", "missing": "H inference is intentionally still data-limited."},
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
        _node("A", (70, 40), "### A — Company Intelligence\n🟡 **CORE / learning TODO**\nEmployer universe + priority\n\nPreference ≠ attainability", "green"),
        _node("B", (345, 40), "### B — Manual Intake\n🟢 **CORE / LIVE**\nManual role = Interested → I\n\nZero-cost salary research", "blue"),
        _node("D", (720, 20), "### D — Remote\n⚪ **SECONDARY / PARTIAL**\nOptional remote candidate lane", "slate"),
        _node("E", (995, 20), "### E — Projects / Interim\n⚪ **SECONDARY / SPARSE**\nOptional project candidate lane", "slate"),
        _node("F", (1270, 20), "### F — People / Network\n⚪ **SECONDARY / DEFERRED**\nOptional access signal", "slate"),
        _node("G", (320, 300), "## G — Aggregated Sourcing Engine\n🟡 **CORE / PARTIAL integration**\nCompany + PE + consulting + sectors + boards\n\nNew candidate roles → C", "amber", width=800, min_height=150),
        _node("C", (500, 550), "## C — Semantic Role Fit\n🟡 **CORE / integration TODO**\nJob content only: Strong / Moderate / Weak\n\nH context never changes fit", "green", width=430, min_height=160),
        _node("COUNTRY", (70, 700), "#### Country Targeting\nSoft weights\n\nSearch effort + diversification\nNever semantic fit", "blue", width=240, min_height=120, source_position="right", target_position="right"),
        _node("J", (500, 785), "## J — Apply Shortlist\n🟢 **CORE / LIVE**\nActionable roles + salary + links\n\nLater: H attainability context", "blue", width=430, min_height=150),
        _node("QUALITY", (1040, 780), "#### Actionability / Quality\n⚪ **NOT BUILT**\nLanguage + geo + link + enrichment gate", "slate", width=250, min_height=120, source_position="left", target_position="left"),
        _node("I", (390, 1035), "## I — History + Feedback Hub\n🟢 **CORE / LIVE store**\nB + J decisions / feedback / stages\n\nActual outcomes → H", "rose", width=440, min_height=155),
        _node("H", (920, 1035), "## H — Attainability\n🟡 **CORE / evidence LIVE, model early**\nInterview → case → final → offer\n\nContext → A / C / G / J", "teal", width=380, min_height=165),
    ]

    edges = [
        _edge("A-G", "A", "G", "company universe / priority", "LIVE"),
        _edge("G-A", "G", "A", "new employers", "PLANNED", kind="feedback"),
        _edge("A-C", "A", "C", "company context only", "PARTIAL", kind="context"),
        _edge("A-J", "A", "J", "company context", "LIVE", kind="context"),
        _edge("A-F", "A", "F", "canonical companies", "LIVE", kind="context"),
        _edge("F-A", "F", "A", "optional access signal", "PARTIAL", kind="feedback"),
        _edge("B-A", "B", "A", "new employer identity", "PARTIAL", kind="context"),
        _edge("I-A", "I", "A", "company preference feedback", "PARTIAL", kind="feedback"),
        _edge("H-A", "H", "A", "employer attainability context", "PLANNED", kind="feedback"),
        _edge("C-G", "C", "G", "future search intelligence", "PARTIAL", kind="feedback"),
        _edge("G-C", "G", "C", "candidate roles", "PARTIAL"),
        _edge("D-C", "D", "C", "optional remote roles", "PARTIAL", kind="context"),
        _edge("E-C", "E", "C", "optional project roles", "PARTIAL", kind="context"),
        _edge("I-C", "I", "C", "role preference learning", "PARTIAL", kind="feedback"),
        _edge("H-C", "H", "C", "role attainability context", "PLANNED", kind="feedback"),
        _edge("C-J", "C", "J", "current-role semantic fit", "PARTIAL"),
        _edge("H-G", "H", "G", "soft search effort", "PLANNED", kind="feedback"),
        _edge("H-J", "H", "J", "attainability / priority context", "PLANNED", kind="feedback"),
        _edge("COUNTRY-G", "COUNTRY", "G", "search weights", "LIVE", kind="context"),
        _edge("COUNTRY-J", "COUNTRY", "J", "diversification", "PARTIAL", kind="context"),
        _edge("QUALITY-J", "QUALITY", "J", "actionability gate", "PLANNED"),
        _edge("B-I", "B", "I", "Interested opportunity", "LIVE"),
        _edge("J-I", "J", "I", "decision + feedback", "LIVE"),
        _edge("I-H", "I", "H", "actual stages + outcomes", "LIVE"),
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
    st.caption("CORE = A/B/C/G/J/I/H. D/E/F are optional secondary lanes. Connection colour = implementation health.")

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
            "professional_dashboard_system_flow_v5",
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
            st.caption("Solid = concrete core candidate/data flow. Dashed = context, learning feedback, secondary lane or planned relation.")
