"""Filter clearly non-actionable language-gated roles before C/J.

This is a feasibility filter, not a semantic-fit rule. It keeps roles whose work
may be attractive out of the actionable J shortlist when the advert explicitly
requires a language the user does not speak at the required level.

Policy:
- English / Czech: never block.
- German: only block when the advert explicitly requires C1/C2, fluent,
  fließend, verhandlungssicher, native or equivalent mother-tongue level.
  B1/B2, "good German" and generic working knowledge remain eligible.
- Other local languages: block when the advert explicitly makes that language
  required / a prerequisite / fluent / professional working proficiency.

The script preserves rows for auditability by changing status from Open to
Pass_language and appending the reason to calibration_note. J and the C queue
already consume only status == Open, so blocked roles disappear upstream.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "jobs_board_staging.csv"

GERMAN_TERMS = ("german", "deutsch", "deutsche", "deutschen", "deutscher")
GERMAN_BLOCK_LEVELS = (
    r"\bc1\b",
    r"\bc2\b",
    r"\bfluent\b",
    r"\bfluency\b",
    r"flie(?:ß|ss)end",
    r"verhandlungssicher",
    r"\bnative\b",
    r"muttersprach",
    r"muttersprache",
)

# English and Czech are intentionally absent. German is handled separately.
OTHER_LANGUAGES = {
    "Norwegian": ("norwegian", "norsk"),
    "Swedish": ("swedish", "svenska"),
    "Danish": ("danish", "dansk"),
    "Finnish": ("finnish", "suomi"),
    "Nordic language": ("nordic language", "scandinavian language"),
    "French": ("french", "français", "francais"),
    "Italian": ("italian", "italiano"),
    "Dutch": ("dutch", "nederlands"),
    "Polish": ("polish", "polski"),
    "Spanish": ("spanish", "español", "espanol"),
}

REQUIREMENT_MARKERS = (
    r"\brequired\b",
    r"\brequirement\b",
    r"\bprerequisite\b",
    r"\bmandatory\b",
    r"\bmust\b",
    r"\bessential\b",
    r"\bfluent\b",
    r"\bfluency\b",
    r"professional (?:working )?proficiency",
    r"business[- ](?:level|fluent)",
    r"native",
    r"mother tongue",
    r"muttersprach",
)


def _text(row: pd.Series) -> str:
    parts = [
        row.get("title", ""),
        row.get("description_en", ""),
        row.get("description", ""),
        row.get("calibration_note", ""),
    ]
    return " ".join(str(x or "") for x in parts)


def _sentences(text: str) -> list[str]:
    # Keep bullet-style requirements separate enough that a language marker is
    # not accidentally paired with an unrelated "required" several paragraphs away.
    return [s.strip().lower() for s in re.split(r"[\n\r•;.!?]+", text) if s.strip()]


def _contains_any(sentence: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in patterns)


def blocking_language_requirement(text: str) -> str:
    sentences = _sentences(text)

    # German exception: B1/B2 and ordinary working/good German are allowed.
    for sentence in sentences:
        if any(term in sentence for term in GERMAN_TERMS) and _contains_any(sentence, GERMAN_BLOCK_LEVELS):
            return "German C1/C2/fluent/native-level requirement"

    # For other languages, require both the language and an explicit requirement
    # marker in the same sentence/bullet. Mere mention of a country/language does
    # not block the role.
    for label, terms in OTHER_LANGUAGES.items():
        for sentence in sentences:
            if any(term in sentence for term in terms) and _contains_any(sentence, REQUIREMENT_MARKERS):
                return f"Mandatory {label} requirement"
    return ""


def apply_filter(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if frame.empty:
        return frame, 0
    out = frame.copy().fillna("")
    if "status" not in out.columns:
        out["status"] = "Open"
    if "calibration_note" not in out.columns:
        out["calibration_note"] = ""

    blocked = 0
    for idx, row in out.iterrows():
        if str(row.get("status", "")) != "Open":
            continue
        reason = blocking_language_requirement(_text(row))
        if not reason:
            continue
        out.at[idx, "status"] = "Pass_language"
        existing = str(row.get("calibration_note", "")).strip()
        note = f"Auto-pass: {reason}"
        out.at[idx, "calibration_note"] = f"{existing}; {note}" if existing else note
        blocked += 1
    return out, blocked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    path = Path(args.path)
    if not path.exists() or path.stat().st_size == 0:
        print(f"language filter: no jobs file at {path}")
        return
    frame = pd.read_csv(path).fillna("")
    filtered, blocked = apply_filter(frame)
    filtered.to_csv(path, index=False)
    print(f"language filter: auto-passed {blocked} roles")


if __name__ == "__main__":
    main()
