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


def _text(row: pd.Series) -> str:
    parts = [
        row.get("title", ""),
        row.get("description_en", ""),
        row.get("description", ""),
        row.get("calibration_note", ""),
    ]
    return " ".join(str(x or "") for x in parts)


def _sentences(text: str) -> list[str]:
    return [s.strip().lower() for s in re.split(r"[\n\r•;.!?]+", text) if s.strip()]


def _language_regex(terms: tuple[str, ...]) -> str:
    return "(?:" + "|".join(re.escape(term) for term in terms) + ")"


def _german_block(sentence: str) -> bool:
    lang = _language_regex(GERMAN_TERMS)
    ordinary_level = re.search(rf"(?:{lang}).{{0,25}}\b(?:b1|b2)\b|\b(?:b1|b2)\b.{{0,25}}(?:{lang})", sentence)
    explicit_high = [
        rf"(?:{lang}).{{0,35}}\b(?:c1|c2)\b",
        rf"\b(?:c1|c2)\b.{{0,35}}(?:{lang})",
        rf"\bfluent\b.{{0,25}}(?:in\s+)?(?:{lang})",
        rf"(?:{lang}).{{0,25}}\bfluent\b",
        rf"\bfluency\s+in\s+(?:{lang})",
        rf"(?:{lang}).{{0,25}}flie(?:ß|ss)end",
        rf"flie(?:ß|ss)end.{{0,25}}(?:{lang})",
        rf"(?:{lang}).{{0,25}}verhandlungssicher",
        rf"verhandlungssicher.{{0,25}}(?:{lang})",
        rf"\bnative\b.{{0,25}}(?:{lang})",
        rf"(?:{lang}).{{0,25}}\bnative\b",
        rf"muttersprach\w*.{{0,25}}(?:{lang})",
        rf"(?:{lang}).{{0,25}}muttersprach\w*",
    ]
    high = any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in explicit_high)
    if ordinary_level and not high:
        return False
    return high


def _other_language_block(sentence: str, terms: tuple[str, ...]) -> bool:
    lang = _language_regex(terms)
    # Remove explicitly negated requirement language before applying positive
    # blocker patterns. This prevents phrases such as "Norwegian is preferred
    # but not mandatory" from being interpreted as a mandatory requirement.
    positive_sentence = re.sub(
        r"\bnot\s+(?:(?:a|an)\s+)?(?:required|mandatory|essential)(?:\s+requirement)?\b",
        "",
        sentence,
        flags=re.IGNORECASE,
    )
    positive_sentence = re.sub(
        r"\b(?:is|are)\s+not\s+(?:required|mandatory|essential)\b",
        "",
        positive_sentence,
        flags=re.IGNORECASE,
    )
    explicit = [
        rf"(?:{lang}).{{0,35}}\b(?:required|mandatory|essential|prerequisite)\b",
        rf"\b(?:required|mandatory|essential)\b.{{0,35}}(?:{lang})",
        rf"\bprerequisite\b.{{0,35}}(?:{lang})",
        rf"\bfluent\b.{{0,25}}(?:in\s+)?(?:{lang})",
        rf"(?:{lang}).{{0,25}}\bfluent\b",
        rf"\bfluency\s+in\s+(?:{lang})",
        rf"professional (?:working )?proficiency.{{0,20}}(?:in\s+)?(?:{lang})",
        rf"(?:{lang}).{{0,20}}professional (?:working )?proficiency",
        rf"business[- ](?:level|fluent).{{0,20}}(?:{lang})",
        rf"(?:{lang}).{{0,20}}business[- ](?:level|fluent)",
        rf"\bnative\b.{{0,25}}(?:{lang})",
        rf"(?:{lang}).{{0,25}}\bnative\b",
        rf"\bmust\b.{{0,20}}(?:speak|know|be fluent in|have).{{0,20}}(?:{lang})",
    ]
    return any(re.search(pattern, positive_sentence, flags=re.IGNORECASE) for pattern in explicit)


def blocking_language_requirement(text: str) -> str:
    sentences = _sentences(text)
    for sentence in sentences:
        if any(term in sentence for term in GERMAN_TERMS) and _german_block(sentence):
            return "German C1/C2/fluent/native-level requirement"
    for label, terms in OTHER_LANGUAGES.items():
        for sentence in sentences:
            if any(term in sentence for term in terms) and _other_language_block(sentence, terms):
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
