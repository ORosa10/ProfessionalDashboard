from __future__ import annotations

import streamlit as st
from streamlit_flow import streamlit_flow

from system_flow_ui import (
    EDGE_DETAILS,
    FLOW_STATE_KEY,
    HEALTH_CONFIG,
    SUPPORT_DETAILS,
    WORKSTREAM_DETAILS,
    _initial_state,
    _reset_flow,
    edge_health,
    health_text,
    node_health,
    node_summary,
    workstream_health_counts,
)

FOCUS_MODE_KEY = "system_flow_focus_mode_v2"
DETAIL_PANEL_KEY = "system_flow_detail_panel"


def _focus_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        .block-container {
            max-width: 100% !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_detail(selected_id: str | None) -> None:
    edge = EDGE_DETAILS.get(selected_id or "")
    if edge:
        st.subheader("Selected connection")
        st.markdown(f"### {selected_id}")
        st.markdown(f"**{health_text(edge_health(selected_id or ''))}**")
        st.markdown(edge["flow"])
        if edge["missing"]:
            st.markdown(f"**Remaining:** {edge['missing']}")
    else:
        info = WORKSTREAM_DETAILS.get(selected_id or "") or SUPPORT_DETAILS.get(selected_id or "")
        st.subheader("Selected node")
        if info:
            st.markdown(f"### {info['title']}")
            st.markdown(f"**{health_text(node_health(selected_id or ''))}**")
            summary = node_summary(selected_id or "")
            if summary:
                st.caption(summary)
            st.markdown(info["purpose"])
            st.markdown(f"**Inputs**  \n{info['inputs']}")
            st.markdown(f"**Outputs**  \n{info['outputs']}")
            st.markdown(f"**Remaining**  \n{info['outstanding']}")
        else:
            st.info("Click any node or connection to inspect its purpose and implementation status.")

    st.divider()
    st.markdown("#### Health legend")
    st.markdown(
        "🟢 **DONE / WORKING** — intended node or connection works  \n"
        "🟠 **IN PROGRESS** — mostly working, but integration or cleanup remains  \n"
        "🔴 **NOT WORKING / NOT ACTIVE** — missing, deferred or not wired"
    )
    st.caption("Solid = core candidate/data flow. Dashed = context, learning feedback, secondary or inactive relation.")

    st.divider()
    st.markdown("#### Architecture")
    st.code(
        "CORE DISCOVERY: A + C → G → C → actionability → J → I\n"
        "MANUAL: B → I\n"
        "PREFERENCE LEARNING: I → A company evidence · I → C role learning\n"
        "OUTCOME LEARNING: I → H → A/C/G/J (future attainability context)\n"
        "SECONDARY: D/E → C optional candidates · F → A/access context"
    )
    st.caption(
        "H never overwrites A preference or C semantic fit. Red H outbound arrows mean the evidence base exists, "
        "but the grouped attainability model is not yet live in those decisions."
    )


def render_system_flow() -> None:
    if FOCUS_MODE_KEY not in st.session_state:
        st.session_state[FOCUS_MODE_KEY] = False
    if DETAIL_PANEL_KEY not in st.session_state:
        st.session_state[DETAIL_PANEL_KEY] = False

    focus_mode = st.session_state[FOCUS_MODE_KEY]
    if focus_mode:
        _focus_css()

    st.markdown('<div class="eyebrow">System architecture</div>', unsafe_allow_html=True)
    st.title("A–J System Flow")
    st.caption(
        f"Current implementation health · updated {HEALTH_CONFIG.get('updated_at', 'unknown')}. "
        "Green = done, orange = in progress, red = not working/not active."
    )

    counts = workstream_health_counts()
    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 Done / working", counts["green"])
    m2.metric("🟠 In progress", counts["orange"])
    m3.metric("🔴 Not working", counts["red"])

    c1, c2, spacer, c4 = st.columns([1.2, 1.3, 5.5, 1.2])
    with c1:
        new_focus = st.toggle("Focus mode", key=FOCUS_MODE_KEY)
    with c2:
        show_detail = st.toggle("Details / legend", key=DETAIL_PANEL_KEY)
    with c4:
        if st.button("Reset layout", use_container_width=True):
            _reset_flow()
            st.rerun()

    if new_focus != focus_mode:
        st.rerun()

    if FLOW_STATE_KEY not in st.session_state:
        st.session_state[FLOW_STATE_KEY] = _initial_state()

    if show_detail:
        canvas, detail = st.columns([5.3, 1.2], gap="medium")
    else:
        canvas = st.container()
        detail = None

    with canvas:
        st.session_state[FLOW_STATE_KEY] = streamlit_flow(
            "professional_dashboard_system_flow_focus_v8",
            st.session_state[FLOW_STATE_KEY],
            fit_view=True,
            height=1040,
            show_controls=True,
            show_minimap=True,
            hide_watermark=True,
            allow_new_edges=False,
            enable_node_menu=False,
            enable_edge_menu=False,
            enable_pane_menu=False,
            get_node_on_click=True,
            get_edge_on_click=True,
            min_zoom=0.2,
        )

    if detail is not None:
        selected_id = getattr(st.session_state[FLOW_STATE_KEY], "selected_id", None)
        with detail:
            _render_detail(selected_id)
