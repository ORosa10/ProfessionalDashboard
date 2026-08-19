from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from github_storage import github_token, load_csv_file, save_csv_file

COMPANY_TARGETING_FEEDBACK_PATH = "data/company_targeting_feedback.csv"
COMPANY_TARGETING_FEEDBACK_COLUMNS = ["submitted_at", "scope", "feedback"]
COMPANY_THESIS_SCOPES = [
    "General (all company types)",
    "Big Four",
    "Consulting",
    "Corporate",
    "Banking & Financial Services",
    "Holding & Conglomerate",
    "Private Equity & Private Markets",
    "Investment Banking",
    "Public Markets & Asset Management",
    "Specialist & Boutique Funds",
]


def render_company_targeting_feedback() -> None:
    with st.expander("Give feedback on the company targeting thesis"):
        st.caption(
            "Tell company discovery what kinds of employers to prioritise or downrank. "
            "For example: 'large multi-country corporates are attractive', "
            "'avoid tiny advisory boutiques', or 'asset managers similar to X are interesting'. "
            "This is company-level feedback for A, separate from the role-level thesis in Jobs."
        )
        scope = st.selectbox(
            "Scope",
            COMPANY_THESIS_SCOPES,
            key="company_thesis_fb_scope",
        )
        feedback_text = st.text_area(
            "Your company thesis feedback",
            key="company_thesis_fb_text",
            placeholder="What should company discovery emphasise or avoid?",
        )
        if st.button(
            "Save company thesis feedback",
            key="company_thesis_fb_save",
            disabled=not feedback_text.strip(),
        ):
            token = github_token()
            if not token:
                st.error("GitHub saving is not configured for this app.")
            else:
                existing, sha = load_csv_file(
                    token,
                    COMPANY_TARGETING_FEEDBACK_PATH,
                    COMPANY_TARGETING_FEEDBACK_COLUMNS,
                )
                new_row = {
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "scope": scope,
                    "feedback": feedback_text.strip(),
                }
                existing = pd.concat(
                    [existing, pd.DataFrame([new_row])],
                    ignore_index=True,
                )
                try:
                    save_csv_file(
                        token,
                        COMPANY_TARGETING_FEEDBACK_PATH,
                        existing,
                        sha,
                        "Add company targeting thesis feedback",
                    )
                except Exception:
                    st.error("Saving failed. Refresh and try again.")
                else:
                    st.success("Saved. It is ready for the next company-thesis calibration.")

        try:
            prior, _ = load_csv_file(
                github_token(),
                COMPANY_TARGETING_FEEDBACK_PATH,
                COMPANY_TARGETING_FEEDBACK_COLUMNS,
            )
        except Exception:
            prior = pd.DataFrame(columns=COMPANY_TARGETING_FEEDBACK_COLUMNS)
        if not prior.empty:
            st.caption("Your company thesis feedback so far:")
            st.dataframe(
                prior.sort_values("submitted_at", ascending=False)[
                    ["scope", "feedback", "submitted_at"]
                ],
                hide_index=True,
                width="stretch",
            )
