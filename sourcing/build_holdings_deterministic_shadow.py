"""Build a read-only holdings source config with deterministic zero-metered-cost paths.

The live holdings source registry currently contains several `adapter=llm` rows.
This shadow helper replaces only sources for which we have a concrete public
career/listing path that can be checked without Gemini or any paid API.

It never writes to the live registry and deliberately leaves unresolved sources
unchanged so the audit can distinguish "deterministic replacement proven" from
"still needs a source-specific solution".
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


OVERRIDES: dict[str, dict[str, str]] = {
    # CSG's corporate career page explicitly routes open roles to its Jobs.cz
    # employer portal. Permit the canonical Jobs.cz detail host as well.
    "csg-global": {
        "seed_url": "https://czechoslovakgroup.jobs.cz/",
        "adapter": "generic",
        "allowed_domains": "czechoslovakgroup.jobs.cz;jobs.cz;www.jobs.cz",
        "shadow_note": "official CSG career page delegates vacancies to Jobs.cz",
    },
    # CPIPG's career page explicitly links the CZ/SK vacancy portal here.
    "cpi-property-group-global": {
        "seed_url": "https://cpi.jobs.cz/",
        "adapter": "generic",
        "allowed_domains": "cpi.jobs.cz;jobs.cz;www.jobs.cz",
        "shadow_note": "official CPIPG career page delegates CZ/SK vacancies to Jobs.cz",
    },
    # Investor AB runs a public Teamtailor career site. The generic crawler can
    # follow /jobs/... links and consume schema.org JobPosting details.
    "investor-ab-global": {
        "seed_url": "https://career.investorab.com/jobs",
        "adapter": "generic",
        "allowed_domains": "career.investorab.com",
        "shadow_note": "official Investor AB Teamtailor jobs page",
    },
    # Industrivarden has a server-rendered recruitment page and a very small
    # organisation. Generic polling is sufficient to detect advertised links.
    "industrivarden-global": {
        "seed_url": "https://www.industrivarden.se/en-gb/operations/organization-and-employees/recruitment/",
        "adapter": "generic",
        "allowed_domains": "industrivarden.se;www.industrivarden.se",
        "shadow_note": "current official recruitment page",
    },
    "kinnevik-global": {
        "seed_url": "https://www.kinnevik.com/working-at-kinnevik/career/",
        "adapter": "generic",
        "allowed_domains": "kinnevik.com;www.kinnevik.com",
        "shadow_note": "current official Kinnevik career page",
    },
    "exor-global": {
        "seed_url": "https://www.exor.com/pages/careers",
        "adapter": "generic",
        "allowed_domains": "exor.com;www.exor.com",
        "shadow_note": "current official EXOR careers page",
    },
    # The old /en/company/career path is stale. The current /en/career page
    # renders vacancy details directly and is suitable for deterministic scan.
    "porsche-se-global": {
        "seed_url": "https://www.porsche-se.com/en/career",
        "adapter": "generic",
        "allowed_domains": "porsche-se.com;www.porsche-se.com",
        "shadow_note": "current official Porsche SE career page",
    },
}


def build_shadow_sources(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.fillna("").copy()
    for column in ("allowed_domains", "shadow_override", "shadow_note"):
        if column not in out.columns:
            out[column] = ""
    for source_id, values in OVERRIDES.items():
        mask = out["source_id"].astype(str).eq(source_id)
        if not mask.any():
            continue
        for key, value in values.items():
            out.loc[mask, key] = value
        out.loc[mask, "shadow_override"] = "deterministic"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source_path = Path(args.sources)
    frame = pd.read_csv(source_path).fillna("") if source_path.exists() and source_path.stat().st_size else pd.DataFrame()
    out = build_shadow_sources(frame)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    overridden = out[out.get("shadow_override", pd.Series("", index=out.index)).eq("deterministic")]
    print(f"holdings deterministic shadow overrides: {len(overridden)}")
    if len(overridden):
        print(overridden[["source_id", "company", "adapter", "seed_url", "shadow_note"]].to_string(index=False))


if __name__ == "__main__":
    main()
