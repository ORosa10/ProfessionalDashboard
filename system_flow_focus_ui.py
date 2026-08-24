from __future__ import annotations

import streamlit as st
from streamlit_flow import streamlit_flow

from system_flow_ui import (
    FLOW_STATE_KEY,
    SUPPORT_DETAILS,
    WORKSTREAM_DETAILS,
    _initial_state,
    _reset_flow,
)

FOCUS_MODE_KEY = "system_flow_focus_mode"
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


def _render_detail(info: dict | None) -> None:
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


def render_system_flow() -> None:
    if FOCUS_MODE_KEY not in st.session_state:
        st.session_state[FOCUS_MODE_KEY] = True
    if DETAIL_PANEL_KEY not in st.session_state:
        st.session_state[DETAIL_PANEL_KEY] = False

    focus_mode = st.session_state[FOCUS_MODE_KEY]
    if focus_mode:
        _focus_css()

    st.markdown('<div class="eyebrow">System architecture</div>', unsafe_allow_html=True)
    st.title("A–J System Flow")
    st.caption(
        "Interactive map of the opportunity engine. Drag nodes, zoom/pan the canvas, "
        "and optionally open the detail panel for a selected workstream."
    )

    c1, c2, spacer, c4 = st.columns([1.2, 1.3, 5.5, 1.2])
    with c1:
        new_focus = st.toggle("Focus mode", key=FOCUS_MODE_KEY)
    with c2:
        show_detail = st.toggle("Details / legend", key=DETAIL_PANEL_KEY)
    with c4:
        if st.button("Reset layout", use_container_width=True):
            _reset_flow()
            st.rerun()

    # The toggle itself triggers a rerun; this keeps the CSS state visually in sync.
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
            "professional_dashboard_system_flow_focus",
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
            get_edge_on_click=False,
            min_zoom=0.2,
        )

    if detail is not None:
        selected_id = getattr(st.session_state[FLOW_STATE_KEY], "selected_id", None)
        info = WORKSTREAM_DETAILS.get(selected_id) or SUPPORT_DETAILS.get(selected_id)
        with detail:
            _render_detail(info)
