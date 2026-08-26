from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState


ROOT = Path(__file__).parent
HEALTH_PATH = ROOT / "data" / "workstream_health.json"

# Bump when the canonical node set changes so stale browser layouts are discarded.
FLOW_STATE_KEY = "professional_dashboard_system_flow_state_v8"

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
    fallback = {"updated_at": "unknown", "legend": {}, "nodes": {}, "edges": {}}
    try:
        payload = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return {**fallback, **payload} if isinstance(payload, dict) else fallback


HEALTH_CONFIG = _load_health()


def node_health(node_id: str) -> str:
    value = str((HEALTH_CONFIG.get("nodes") or {}).get(node_id, {}).get("health", "orange")).lower()
    return value if value in STATUS_META else "orange"


def node_summary(node_id: str) -> str:
    return str((HEALTH_CONFIG.get("nodes") or {}).get(node_id, {}).get("summary", ""))


def edge_health(edge_id: str) -> str:
    value = str((HEALTH_CONFIG.get("edges") or {}).get(edge_id, "orange")).lower()
    return value if value in STATUS_META else "orange"


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
        "purpose": "Maintain the employer universe and explicit company priority.",
        "inputs": "User ratings/notes + employers discovered in G + factual learning evidence from I.",
        "outputs": "Company universe/context → G and J; new employers → A review.",
        "outstanding": "No core blocker.",
    },
    "B": {
        "title": "B — Manual Opportunity Intake",
        "purpose": "Capture roles already found/applied to manually.",
        "inputs": "Vacancy URL + optional comment.",
        "outputs": "Apply / Applied fact → I; employer can surface in A.",
        "outstanding": "No core blocker.",
    },
    "C": {
        "title": "C — Semantic Role Fit",
        "purpose": "Judge only whether actual day-to-day work is Strong / Moderate / Weak semantic fit.",
        "inputs": "Concrete roles from G plus controlled role-learning evidence from I.",
        "outputs": "Strong roles → existing actionability checks → J.",
        "outstanding": "Run a clean replenishment after the latest metadata-preservation fixes.",
    },
    "D": {
        "title": "D — Remote",
        "purpose": "Secondary remote-role discovery lane.",
        "inputs": "Remote job sources.",
        "outputs": "Optional candidates → C.",
        "outstanding": "Secondary; not required for the core G→C→J flow.",
    },
    "E": {
        "title": "E — Projects / Interim",
        "purpose": "Secondary project/contract/interim lane.",
        "inputs": "Project/interim sources.",
        "outputs": "Optional candidates → C.",
        "outstanding": "Secondary and sparse.",
    },
    "F": {
        "title": "F — People / Network",
        "purpose": "Optional network/access context.",
        "inputs": "Connection data.",
        "outputs": "Optional access context → A.",
        "outstanding": "Deferred; no live connection dataset.",
    },
    "G": {
        "title": "G — Sourcing Engine",
        "purpose": "Find vacancies through target-company career sites and country/job-board searches.",
        "inputs": "A employer universe + C search concepts + country weights + configured sources.",
        "outputs": "Candidate roles → C; discovered employers → A.",
        "outstanding": "Confirm stale-link revalidation in production; credential-only sources are intentionally deferred.",
    },
    "H": {
        "title": "H — Attainability",
        "purpose": "Learn attainability from actual application outcomes.",
        "inputs": "Lifecycle outcomes from I.",
        "outputs": "Later attainability context without changing A preference or C semantic fit.",
        "outstanding": "Needs more outcome data; not a technical blocker today.",
    },
    "I": {
        "title": "I — Opportunity & Application History",
        "purpose": "Canonical factual memory of decisions and application lifecycle events.",
        "inputs": "B manual applications + J decisions + later outcome updates.",
        "outputs": "Factual evidence → A/C/H.",
        "outstanding": "No core blocker.",
    },
    "J": {
        "title": "J — Apply Shortlist",
        "purpose": "Final actionable working queue.",
        "inputs": "C=Strong + existing actionability/link/geography guardrails + company/country context.",
        "outputs": "Apply / Maybe / Skip → I.",
        "outstanding": "No separate quality workstream; safeguards are part of the existing G→C→J path.",
    },
}

SUPPORT_DETAILS = {
    "COUNTRY": {
        "title": "Country Targeting",
        "purpose": "Soft weights guide sourcing effort and shortlist diversification.",
        "inputs": "Target-country weights.",
        "outputs": "Search allocation → G; soft context → J.",
        "outstanding": "No core blocker.",
    }
}

EDGE_DETAILS = {
    "A-G": {"flow": "Rated employers and career URLs feed recurring company-driven sourcing.", "missing": ""},
    "G-A": {"flow": "New employers found by G surface in A as Unrated suggestions.", "missing": ""},
    "A-C": {"flow": "Company identity accompanies roles as context only.", "missing": ""},
    "A-J": {"flow": "Company context is available in J.", "missing": ""},
    "A-F": {"flow": "Canonical employers can later feed the optional network lane.", "missing": "F is deferred."},
    "F-A": {"flow": "Network access could later inform A context.", "missing": "No live network data."},
    "B-A": {"flow": "Employers from manual applications can surface in A.", "missing": ""},
    "I-A": {"flow": "Explicit company feedback from history becomes factual A evidence.", "missing": ""},
    "H-A": {"flow": "Later attainability context may inform A without changing preference.", "missing": "H is data-limited."},
    "C-G": {"flow": "Stable C learning may add approved search concepts to G.", "missing": "Only stable approved guidance is activated."},
    "G-C": {"flow": "G sends concrete candidate roles into C.", "missing": ""},
    "D-C": {"flow": "Remote roles may use C semantic classification.", "missing": "Secondary lane."},
    "E-C": {"flow": "Project/interim roles may use C semantic classification.", "missing": "Secondary lane."},
    "I-C": {"flow": "Explicit role-content feedback becomes C learning evidence.", "missing": ""},
    "H-C": {"flow": "Later attainability context remains separate from C fit.", "missing": "H is data-limited."},
    "C-J": {"flow": "C=Strong roles that pass existing actionability safeguards feed J.", "missing": ""},
    "H-G": {"flow": "H may later soft-reweight search effort.", "missing": "No live H reweighting."},
    "H-J": {"flow": "H may later add attainability context to J.", "missing": "No live H signal in J."},
    "COUNTRY-G": {"flow": "Country weights guide G sourcing effort.", "missing": ""},
    "COUNTRY-J": {"flow": "Country mix is soft context in J.", "missing": ""},
    "B-I": {"flow": "Manual applications reconcile directly into canonical I.", "missing": ""},
    "J-I": {"flow": "J decisions and feedback are saved into I.", "missing": ""},
    "I-H": {"flow": "Actual stages/outcomes provide H evidence.", "missing": "Inference remains data-limited."},
}
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
    return StreamlitFlowNode(
        id=node_id,
        pos=pos,
        data={"content": f"### {title}\n{meta['icon']} **{meta['label']}**\n{description}"},
        node_type="default",
        source_position=source_position,
        target_position=target_position,
        draggable=True,
        selectable=True,
        connectable=False,
        deletable=False,
        style=_style(health, width, min_height),
    )


def _edge(edge_id: str, source: str, target: str, label: str, *, kind: str = "data") -> StreamlitFlowEdge:
    health = edge_health(edge_id)
    meta = STATUS_META[health]
    style = {"stroke": meta["edge"], "strokeWidth": 2.6}
    if kind != "data" or health == "red":
        style["strokeDasharray"] = "7 5"
    return StreamlitFlowEdge(
        id=edge_id,
        source=source,
        target=target,
        edge_type="smoothstep",
        marker_end={"type": "arrowclosed", "color": meta["edge"]},
        animated=health == "green" and kind == "data",
        label=f"{meta['icon']} {label}",
        label_style={"fill": meta["edge"], "fontWeight": 700, "fontSize": 9},
        label_show_bg=True,
        label_bg_style={"fill": "#FFFFFF", "fillOpacity": 0.94},
        style=style,
    )


def _initial_state() -> StreamlitFlowState:
    nodes = [
        _node("A", (70, 40), "A — Company Intelligence", "Employer universe + explicit priority", width=245),
        _node("B", (350, 40), "B — Manual Intake", "Manual applied roles → I", width=245),
        _node("D", (720, 20), "D — Remote", "Secondary remote lane", width=235),
        _node("E", (990, 20), "E — Projects / Interim", "Secondary project/interim lane", width=245),
        _node("F", (1270, 20), "F — People / Network", "Deferred network layer", width=245),
        _node("G", (320, 300), "G — Sourcing Engine", "Company career sites + job boards\n\nCandidate roles → C · new employers → A", width=800, min_height=155),
        _node("C", (500, 550), "C — Semantic Role Fit", "Actual job content only: Strong / Moderate / Weak", width=430, min_height=150),
        _node("COUNTRY", (70, 700), "Country Targeting", "Soft sourcing weights", width=240, min_height=120, source_position="right", target_position="right"),
        _node("J", (500, 785), "J — Apply Shortlist", "C=Strong + actionable/current roles\n\nApply / Maybe / Skip → I", width=430, min_height=150),
        _node("I", (390, 1035), "I — Application / History", "Canonical decisions + lifecycle events\n\nEvidence → A/C/H", width=440, min_height=165),
        _node("H", (920, 1035), "H — Attainability", "Outcome evidence\n\nInference waits for enough data", width=390, min_height=165),
    ]
    edges = [
        _edge("A-G", "A", "G", "company universe / career sources"),
        _edge("G-A", "G", "A", "new employers", kind="feedback"),
        _edge("A-C", "A", "C", "company identity", kind="context"),
        _edge("A-J", "A", "J", "company context", kind="context"),
        _edge("A-F", "A", "F", "canonical companies", kind="context"),
        _edge("F-A", "F", "A", "optional access", kind="feedback"),
        _edge("B-A", "B", "A", "new employer", kind="context"),
        _edge("I-A", "I", "A", "company evidence", kind="feedback"),
        _edge("H-A", "H", "A", "attainability", kind="feedback"),
        _edge("C-G", "C", "G", "approved search learning", kind="feedback"),
        _edge("G-C", "G", "C", "candidate roles"),
        _edge("D-C", "D", "C", "remote roles", kind="context"),
        _edge("E-C", "E", "C", "project roles", kind="context"),
        _edge("I-C", "I", "C", "role learning", kind="feedback"),
        _edge("H-C", "H", "C", "attainability", kind="feedback"),
        _edge("C-J", "C", "J", "Strong + existing safeguards"),
        _edge("H-G", "H", "G", "future search context", kind="feedback"),
        _edge("H-J", "H", "J", "future attainability", kind="feedback"),
        _edge("COUNTRY-G", "COUNTRY", "G", "search weights", kind="context"),
        _edge("COUNTRY-J", "COUNTRY", "J", "country context", kind="context"),
        _edge("B-I", "B", "I", "manual application"),
        _edge("J-I", "J", "I", "decision + feedback"),
        _edge("I-H", "I", "H", "actual outcomes"),
    ]
    return StreamlitFlowState(nodes, edges)


def _reset_flow() -> None:
    st.session_state[FLOW_STATE_KEY] = _initial_state()
