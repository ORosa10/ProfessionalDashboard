from __future__ import annotations

import re

import pandas as pd

# Language of the advert is only a soft actionability signal. It never changes C
# and never hard-blocks a role; explicit language requirements are handled by the
# existing actionability filter.
GERMAN_MARKERS = {
    "der", "die", "das", "und", "mit", "für", "von", "bei", "wir", "sie",
    "ihre", "ihren", "unser", "unsere", "aufgaben", "aufgabe", "profil",
    "erfahrung", "kenntnisse", "bereich", "unternehmen", "verantwortung",
    "bewerbung", "stellen", "arbeiten", "arbeit", "sowie", "durch", "einen",
    "eine", "einem", "einer", "zum", "zur",
}
SWEDISH_MARKERS = {
    "och", "att", "du", "vi", "din", "dina", "har", "inom", "erfarenhet",
    "arbetsuppgifter", "rollen", "söker", "kunskaper", "arbete", "företag",
    "ansvar", "samt", "med", "för", "som", "likviditet", "finansiell",
}
NORWEGIAN_MARKERS = {
    "og", "at", "du", "vi", "din", "dine", "har", "innen", "erfaring",
    "arbeidsoppgaver", "rollen", "søker", "kunnskap", "arbeid", "selskap",
    "ansvar", "samt", "med", "for", "som", "finansiell",
}
DANISH_MARKERS = {
    "og", "at", "du", "vi", "din", "dine", "har", "inden", "erfaring",
    "arbejdsopgaver", "rollen", "søger", "kendskab", "arbejde", "virksomhed",
    "ansvar", "samt", "med", "for", "som", "finansiel",
}
FINNISH_MARKERS = {
    "ja", "että", "sinä", "me", "kokemus", "tehtävä", "tehtävät", "haemme",
    "osaaminen", "työ", "yritys", "vastuu", "sekä", "kanssa", "varten",
    "rahoitus", "talous", "sijoitus",
}
FRENCH_MARKERS = {
    "nous", "vous", "avec", "pour", "dans", "expérience", "poste", "profil",
    "entreprise", "responsabilités", "connaissances", "travail", "équipe",
    "ainsi", "financier", "financière",
}
ITALIAN_MARKERS = {
    "noi", "voi", "con", "per", "nel", "nella", "esperienza", "ruolo",
    "profilo", "azienda", "responsabilità", "conoscenze", "lavoro", "team",
    "finanziario", "finanziaria",
}

COUNTRY_LANGUAGE_MARKERS: dict[str, tuple[set[str], ...]] = {
    "Germany": (GERMAN_MARKERS,),
    "Austria": (GERMAN_MARKERS,),
    "Switzerland": (GERMAN_MARKERS, FRENCH_MARKERS, ITALIAN_MARKERS),
    "Sweden": (SWEDISH_MARKERS,),
    "Norway": (NORWEGIAN_MARKERS,),
    "Denmark": (DANISH_MARKERS,),
    "Finland": (FINNISH_MARKERS,),
}

SENIORITY_SOFT_2 = re.compile(r"\b(lead|team lead|teamleiter(?:in)?|leiter(?:in)?)\b", re.IGNORECASE)
MANAGER_PATTERN = re.compile(r"\bmanager\b", re.IGNORECASE)
SENIOR_PATTERN = re.compile(r"\bsenior\b", re.IGNORECASE)
SENIOR_ANALYST_PATTERN = re.compile(r"\bsenior\s+analyst\b", re.IGNORECASE)

EXPERIENCE_PATTERNS = [
    re.compile(r"\b(?:minimum(?:\s+of)?|at\s+least|at\s+a\s+minimum|min\.?)\s+(\d{1,2})\+?\s+years?\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\+\s+years?\s+(?:of\s+)?(?:relevant\s+|professional\s+)?experience\b", re.IGNORECASE),
    re.compile(r"\bmindestens\s+(\d{1,2})\s+jahre\b", re.IGNORECASE),
    re.compile(r"\bminst\s+(\d{1,2})\s+års?\b", re.IGNORECASE),
]


def _looks_like_language(text: object, markers: set[str]) -> bool:
    raw = str(text or "").lower()
    if not raw:
        return False
    tokens = set(re.findall(r"[a-zà-öø-ÿäöüßåæø]+", raw))
    return len(tokens.intersection(markers)) >= 6


def looks_german_advert(text: object) -> bool:
    return _looks_like_language(text, GERMAN_MARKERS)


def language_soft_penalty(row: pd.Series) -> int:
    country = str(row.get("country_bucket", "") or row.get("market", "") or "").strip()
    marker_sets = COUNTRY_LANGUAGE_MARKERS.get(country, ())
    if not marker_sets:
        return 0
    # Use the original advert, not description_en, because translated text must
    # not hide the practical signal that the employer chose to advertise locally.
    original = row.get("description", "")
    return 1 if any(_looks_like_language(original, markers) for markers in marker_sets) else 0


def title_seniority_soft_penalty(title: object) -> int:
    value = str(title or "")
    if SENIORITY_SOFT_2.search(value):
        return 2
    if MANAGER_PATTERN.search(value):
        return 1
    # Senior Analyst remains inside the target band; other Senior titles get a
    # mild downgrade rather than being excluded.
    if SENIOR_PATTERN.search(value) and not SENIOR_ANALYST_PATTERN.search(value):
        return 1
    return 0


def explicit_experience_soft_penalty(text: object) -> int:
    raw = str(text or "")
    required_years: list[int] = []
    for pattern in EXPERIENCE_PATTERNS:
        required_years.extend(int(x) for x in pattern.findall(raw))
    if not required_years:
        return 0
    years = max(required_years)
    if years >= 8:
        return 2
    if years >= 6:
        return 1
    return 0


def seniority_soft_penalty(title: object, description: object = "") -> int:
    return max(title_seniority_soft_penalty(title), explicit_experience_soft_penalty(description))


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
    out["_seniority_soft"] = out.apply(
        lambda row: seniority_soft_penalty(row.get("title", ""), row.get("description", "")),
        axis=1,
    )
    return out
