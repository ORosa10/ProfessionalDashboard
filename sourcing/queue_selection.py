from __future__ import annotations

import pandas as pd


def select_country_balanced_indices(
    jobs: pd.DataFrame,
    limit: int,
    targets: dict[str, int],
    family_cap: int = 18,
) -> list[int]:
    """Select a bounded C queue without letting country order starve later markets.

    Country allocation is the primary workload-shaping rule. Role-family diversity
    is applied only to the fallback capacity after each country has had a chance to
    fill its soft target. A final uncapped pass guarantees that available capacity
    is never left unused.
    """
    if jobs.empty or limit <= 0:
        return []

    desired = min(limit, len(jobs))
    chosen: list[int] = []
    chosen_set: set[int] = set()
    family_counts: dict[str, int] = {}

    def add(idx: int, row: pd.Series) -> bool:
        if idx in chosen_set or len(chosen) >= desired:
            return False
        chosen.append(idx)
        chosen_set.add(idx)
        family = str(row.get("role_family", "Other finance") or "Other finance")
        family_counts[family] = family_counts.get(family, 0) + 1
        return True

    # First honour every country's soft allocation. Do not apply a global family
    # cap here: doing so made the result depend on country iteration order and
    # previously starved Denmark / Finland after earlier markets consumed a family.
    for country, target in targets.items():
        if target <= 0 or len(chosen) >= desired:
            continue
        filled = 0
        country_pool = jobs[jobs["market"].astype(str).eq(str(country))]
        for idx, row in country_pool.iterrows():
            if add(idx, row):
                filled += 1
            if filled >= target or len(chosen) >= desired:
                break

    # Then use remaining capacity with the existing global family-diversity cap.
    if len(chosen) < desired:
        for idx, row in jobs.iterrows():
            if idx in chosen_set:
                continue
            family = str(row.get("role_family", "Other finance") or "Other finance")
            if family_counts.get(family, 0) >= family_cap:
                continue
            add(idx, row)
            if len(chosen) >= desired:
                break

    # Sparse countries / concentrated role families should not leave queue slots
    # empty. Quality order from the caller is preserved in this final fill.
    if len(chosen) < desired:
        for idx, row in jobs.iterrows():
            add(idx, row)
            if len(chosen) >= desired:
                break

    return chosen
