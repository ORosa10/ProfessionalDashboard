from __future__ import annotations

ENGLISH_INTENT_COUNTRIES = {
    "Germany", "Austria", "Switzerland", "Sweden", "Norway", "Denmark", "Finland",
}

# These supplement, rather than replace, the broad semantic discovery vocabulary.
# They are sourcing hints only: C still judges role fit independently.
ENGLISH_INTENT_QUERIES = [
    "treasury english",
    "corporate finance english",
    "investment analyst english",
    "market risk english",
    "M&A english",
    "portfolio manager english",
]


def queries_for_country(base_queries: list[str], country: object) -> list[str]:
    queries = list(base_queries)
    if str(country or "").strip() in ENGLISH_INTENT_COUNTRIES:
        queries.extend(ENGLISH_INTENT_QUERIES)
    return list(dict.fromkeys(str(q).strip() for q in queries if str(q).strip()))
