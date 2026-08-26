from __future__ import annotations

import re

import pandas as pd

DACH_COUNTRIES = {"Germany", "Austria", "Switzerland"}

# This is deliberately a language-of-advert signal, not a language requirement
# parser. Explicit requirements remain the responsibility of actionability.
GERMAN_MARKERS = {
    "der", "die", "das", "und", "mit", "für", "von", "bei", "wir", "sie",
    "ihre", "ihren", "unser", "unsere", "aufgaben", "aufgabe", "profil",
    "erfahrung", "kenntnisse", "bereich", "unternehmen", "verantwortung",
    "bewerbung", "stellen", "arbeiten", "arbeit", "sowie", "durch", "einen",
    "eine", "einem", "einer", "zum", "zur",
}

SENIORITY_SOFT_2 = re.compile(r"\b(lead|team lead|teamleiter(?:in)?|leiter(?:in)?)\b", re.IGNORECASE)
SENIORITY_SOFT_1 = re.compile(
    r"\b(manager|senior consultant|senior specialist|senior advisor|senior adviser)\b",
    re.IGNORECASE,
)


def looks_german_advert(text: object) -> bool:
    raw = str(text or "").lower()
    if not raw:
        return False
    tokens = set(re.findall(r"[a-zäöüß]+", raw))
    marker_hits = len(tokens.intersection(GERMAN_MARKERS))
    # Requiring several distinct function / job-ad words makes this robust to
    # isolated German company or location names inside otherwise English ads.
    return marker_hits >= 6


def language_soft_penalty(row: pd.Series) -> int:
    country = str(row.get("country_bucket", "") or row.get("market", "") or "").strip()
    if country not in DACH_COUNTRIES:
        return 0
    # Use the original advert, not description_en, because translated text must
    # not hide the practical signal that the employer chose to advertise locally.
    return 1 if looks_german_advert(row.get("description", "")) else 0


def seniority_soft_penalty(title: object) -> int:
    value = str(title or "")
    if SENIORITY_SOFT_2.search(value):
        return 2
    if SENIORITY_SOFT_1.search(value):
        return 1
    return 0


def add_soft_rank_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "description" not in out.columns:
        out["description"] = ""
    if "country_bucket" not in out.columns:
        out["country_bucket"] = ""
    if "market" not in out.columns:
        out["market"] = ""
    if "title" not in out.columns:
        out["title"] = ""
    out["_language_soft"] = out.apply(language_soft_penalty, axis=1)
    out["_seniority_soft"] = out["title"].map(seniority_soft_penalty)
    return out
