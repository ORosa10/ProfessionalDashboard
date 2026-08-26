from __future__ import annotations

import unittest

import pandas as pd

from sourcing.reconcile_i_learning import (
    EVENT_COLUMNS,
    HISTORY_COLUMNS,
    build_learning,
    reconcile_events,
    reconcile_history,
)


class CanonicalILearningTests(unittest.TestCase):
    def test_manual_b_becomes_canonical_applied(self) -> None:
        submissions = pd.DataFrame([{
            "submission_id": "abc", "submitted_at": "2026-08-26T10:00:00+00:00",
            "title": "Treasury Analyst", "company": "Example AG", "country": "Germany",
            "location": "Berlin", "job_url": "https://example.com/job", "user_comment": "good treasury role",
            "source_domain": "example.com",
        }])
        out = reconcile_history(pd.DataFrame(columns=HISTORY_COLUMNS), submissions)
        row = out.iloc[0]
        self.assertEqual(row["opportunity_id"], "B:abc")
        self.assertEqual(row["action"], "Apply")
        self.assertEqual(row["application_stage"], "Applied")
        self.assertEqual(row["role_feedback"], "Positive")

    def test_manual_b_does_not_roll_back_advanced_stage(self) -> None:
        history = pd.DataFrame([{c: "" for c in HISTORY_COLUMNS}])
        history.loc[0, ["opportunity_id", "source_stream", "application_stage", "stage_updated_at"]] = [
            "B:abc", "B", "Case", "2026-08-27T10:00:00+00:00"
        ]
        submissions = pd.DataFrame([{"submission_id": "abc", "submitted_at": "2026-08-26T10:00:00+00:00"}])
        out = reconcile_history(history, submissions)
        self.assertEqual(out.iloc[0]["application_stage"], "Case")

    def test_events_append_on_real_state_change_only(self) -> None:
        row = {c: "" for c in HISTORY_COLUMNS}
        row.update({
            "opportunity_id": "x", "source_stream": "G", "first_seen_at": "2026-08-26T10:00:00+00:00",
            "decision_at": "2026-08-26T10:10:00+00:00", "action": "Apply", "role_feedback": "Positive",
            "application_stage": "Applied", "stage_updated_at": "2026-08-26T10:10:00+00:00",
        })
        history = pd.DataFrame([row])
        first = reconcile_events(history, pd.DataFrame(columns=EVENT_COLUMNS))
        self.assertEqual(set(first["event_type"]), {"opportunity_created", "decision", "application_stage"})
        same = reconcile_events(history, first)
        self.assertEqual(len(same), len(first))
        history.loc[0, "application_stage"] = "1st interview"
        history.loc[0, "stage_updated_at"] = "2026-08-28T10:00:00+00:00"
        changed = reconcile_events(history, same)
        self.assertEqual(len(changed), len(first) + 1)
        self.assertEqual(changed.iloc[-1]["application_stage"], "1st interview")

    def test_learning_separates_a_c_h(self) -> None:
        history = pd.DataFrame([{c: "" for c in HISTORY_COLUMNS}])
        history.loc[0, [
            "opportunity_id", "company", "canonical_company_id", "company_category", "title", "market"
        ]] = ["x", "Example AG", "example", "Corporate", "Treasury Analyst", "Germany"]
        events = pd.DataFrame([
            {
                "event_id": "d1", "opportunity_id": "x", "event_at": "2026-08-26T10:00:00+00:00",
                "event_type": "decision", "source_stream": "G", "action": "Skip",
                "application_stage": "", "company_feedback": "Negative", "role_feedback": "Negative",
                "user_comment": "too much reporting", "outcome_reason": "", "notes": "",
            },
            {
                "event_id": "s1", "opportunity_id": "x", "event_at": "2026-08-27T10:00:00+00:00",
                "event_type": "application_stage", "source_stream": "G", "action": "",
                "application_stage": "1st interview", "company_feedback": "", "role_feedback": "",
                "user_comment": "", "outcome_reason": "", "notes": "",
            },
        ]).reindex(columns=EVENT_COLUMNS, fill_value="")
        a_events, a_summary, c_events, h_events, h_summary = build_learning(history, events)
        self.assertEqual(len(a_events), 1)
        self.assertEqual(c_events.iloc[0]["c_signal"], "negative")
        self.assertEqual(h_events.iloc[0]["h_evidence"], "reached_interview")
        market = h_summary[(h_summary["dimension"] == "market") & (h_summary["value"] == "Germany")].iloc[0]
        self.assertEqual(int(market["reached_interview"]), 1)


if __name__ == "__main__":
    unittest.main()
