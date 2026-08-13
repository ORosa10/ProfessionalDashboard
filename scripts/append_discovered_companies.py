"""Append newly-researched candidate companies (found by parallel research
agents) into the correct company_universe_wave*.csv files as new, Unrated
rows -- ready for the user to rate in the Companies page of the app.

This does NOT touch data/company_ratings.csv (that's populated only by the
Streamlit app when the user actually rates a company) and does NOT run any
sourcing -- scripts/build_sector_sources.py picks these up automatically
once they're rated (rating != "" and != "Exclude").
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

EXISTING_IDS = set(pd.read_csv(DATA / "company_ratings.csv").fillna("")["canonical_company_id"])

UNIVERSE_COLUMNS = [
    "canonical_company_id", "company", "parent_company_id", "aliases_entities",
    "company_category", "region", "locations", "archetype", "why_test",
    "career_url", "source_strategy", "rating", "notes",
]

# (target wave file, category, rows). career_url left blank when the
# research agent could not verify an official first-party URL -- better
# blank than a guessed/fabricated link.
BATCHES = [
    ("company_universe_wave2_consulting.csv", "Consulting", [
        dict(canonical_company_id="kroll", company="Kroll", region="Multi-region",
             locations="London; Frankfurt; Zurich; Paris; Luxembourg",
             archetype="Financial & Valuation Advisory",
             why_test="Global valuation, financial risk, restructuring and derivatives advisory firm hiring across treasury/valuation/risk practices in UK, DACH and other EU offices.",
             career_url="https://careers.kroll.com/en", source_strategy="Official careers page (Oracle Cloud ATS)"),
        dict(canonical_company_id="lincoln-international", company="Lincoln International", region="Multi-region",
             locations="Frankfurt; Vienna; Zurich; London",
             archetype="Mid-Market M&A Advisory / Investment Banking",
             why_test="Mid-market M&A and valuation advisory with offices across DACH/UK relevant to deals and valuation experience.",
             career_url="https://www.lincolninternational.com/careers-and-culture/careers/", source_strategy="Official careers page"),
        dict(canonical_company_id="interpath-advisory", company="Interpath Advisory", region="United Kingdom",
             locations="London; Munich",
             archetype="Restructuring & Financial Advisory (ex-KPMG UK spin-off)",
             why_test="Restructuring/insolvency and financial advisory firm expanding into DACH, fitting treasury/liquidity/risk turnaround work.",
             career_url="", source_strategy="No confirmed direct careers URL yet; check job boards"),
        dict(canonical_company_id="berkeley-research-group", company="Berkeley Research Group", region="United Kingdom",
             locations="London",
             archetype="Financial Consulting / Disputes & Valuation",
             why_test="Disputes, valuation and financial consulting practice suits derivatives/valuation background.",
             career_url="", source_strategy="No confirmed direct careers URL yet; check job boards"),
        dict(canonical_company_id="ankura-consulting-group", company="Ankura Consulting Group", region="United Kingdom",
             locations="London",
             archetype="Financial Advisory / Risk & Disputes Consulting",
             why_test="Financial advisory, risk, and restructuring consulting practice relevant to market risk and treasury profile.",
             career_url="", source_strategy="No confirmed direct careers URL yet; check job boards"),
        dict(canonical_company_id="teneo", company="Teneo", region="Multi-region",
             locations="London",
             archetype="CEO / Financial & Risk Advisory",
             why_test="Dedicated Financial Advisory and Risk Advisory practice lines fit restructuring, treasury and risk experience.",
             career_url="https://www.teneo.com/careers/open-positions/", source_strategy="Official careers page"),
        dict(canonical_company_id="wtw", company="WTW (Willis Towers Watson)", region="Multi-region",
             locations="London; Frankfurt; Zurich; Stockholm; Copenhagen",
             archetype="Investment & Risk Consulting",
             why_test="Investment consulting and risk management advisory practices align with market risk, treasury and investment experience.",
             career_url="https://careers.wtwco.com/", source_strategy="Official careers page"),
    ]),
    ("company_universe_wave2_corporate.csv", "Corporate", [
        dict(canonical_company_id="yara-international", company="Yara International", region="Norway", locations="Oslo",
             archetype="Chemicals / Agri-Industrial - Corporate Finance & Treasury",
             why_test="Global fertilizer/chemicals producer with heavy FX, commodity-price and interest-rate exposure, requiring active treasury, hedging and risk functions.",
             career_url="https://jobs.yara.com/", source_strategy="Official careers page"),
        dict(canonical_company_id="coloplast", company="Coloplast", region="Denmark", locations="Humlebæk; Copenhagen",
             archetype="Medtech / Consumer Health - Corporate Finance",
             why_test="Large-cap Danish medtech exporter with multi-currency revenue base, well-suited to FP&A, treasury and financial risk roles.",
             career_url="https://careers.coloplast.com/", source_strategy="Official careers portal"),
        dict(canonical_company_id="sandvik", company="Sandvik", region="Sweden", locations="Stockholm; Sandviken",
             archetype="Industrial Engineering - Corporate Finance & Treasury",
             why_test="Diversified global industrial group with a dedicated Group Treasury entity and finance career track covering FP&A, treasury and risk.",
             career_url="https://www.home.sandvik/en/careers/", source_strategy="Filter 'Finance' job area on official careers site"),
        dict(canonical_company_id="fresenius", company="Fresenius", region="Germany", locations="Bad Homburg; Frankfurt",
             archetype="Healthcare / Pharma-adjacent - Corporate Treasury & Capital Markets",
             why_test="Large, leveraged German healthcare group with an active Treasury Capital Markets function, matching derivatives, liquidity and debt-market experience.",
             career_url="https://karriere.fresenius.de/en-US/", source_strategy="Official careers portal"),
        dict(canonical_company_id="linde", company="Linde plc", region="Multi-region", locations="Munich; Dublin; London",
             archetype="Industrial Gases - Corporate Finance / Treasury / IR",
             why_test="Large-cap industrial gases multinational with major German operating base and dual UK/Ireland listing structure, needing sophisticated treasury and hedging capability.",
             career_url="https://www.lindecareers.com/en/", source_strategy="Official careers portal"),
        dict(canonical_company_id="vodafone-group", company="Vodafone Group", region="United Kingdom", locations="London; Newbury",
             archetype="Telecommunications - Corporate Finance / Treasury",
             why_test="UK-headquartered multinational telecom with a large Group Treasury and Finance function fitting corporate finance and risk profiles.",
             career_url="https://careers.vodafone.co.uk/Finance-jobs", source_strategy="Dedicated Finance-jobs filter"),
        dict(canonical_company_id="voestalpine", company="voestalpine AG", region="Austria", locations="Linz; Vienna",
             archetype="Steel & Advanced Materials - Corporate Finance & Treasury",
             why_test="Large-cap Austrian industrial/steel group with export-driven, commodity- and FX-sensitive operations requiring treasury and financial risk expertise.",
             career_url="https://www.voestalpine.com/group/en/jobs/", source_strategy="Official careers page"),
        dict(canonical_company_id="sika", company="Sika AG", region="Switzerland", locations="Baar/Zug; Zurich",
             archetype="Specialty Chemicals / Construction Materials - Corporate Finance & Treasury",
             why_test="Swiss specialty-chemicals multinational with global M&A-driven growth strategy, generating demand for corporate finance, treasury and FX/commodity risk roles.",
             career_url="https://www.sika.com/en/career.html", source_strategy="Official careers page"),
    ]),
    ("company_universe_wave2_financial_services.csv", "Banking & Financial Services", [
        dict(canonical_company_id="komercni-banka", company="Komerční banka", region="Czechia", locations="Prague",
             archetype="Retail & Corporate Banking / Treasury / Risk",
             why_test="Major Czech universal bank (Société Générale group) with active treasury, market risk, and corporate finance functions in the home market.",
             career_url="https://kariera.kb.cz/", source_strategy="Job board; filter treasury/risk/finance"),
        dict(canonical_company_id="nykredit", company="Nykredit", region="Denmark", locations="Copenhagen",
             archetype="Mortgage Banking / Treasury / Financial Risk",
             why_test="Denmark's largest mortgage lender with heavy interest-rate risk, funding/treasury, and covered-bond activities matching rates/liquidity background.",
             career_url="https://www.nykredit.com/en-gb/career/karriereveje/", source_strategy="Career portal + LinkedIn"),
        dict(canonical_company_id="sparebank-1", company="SpareBank 1", region="Norway", locations="Oslo; Trondheim; Bergen; Tromsø",
             archetype="Banking Alliance / Treasury / Risk",
             why_test="Large Norwegian bank alliance with treasury, ALM, and market-risk roles across its group and regional banks.",
             career_url="https://www.sparebank1.no/nb/bank/om-oss/jobb-og-karriere.html", source_strategy="Group careers page + member-bank sites"),
        dict(canonical_company_id="lansforsakringar", company="Länsförsäkringar", region="Sweden", locations="Stockholm",
             archetype="Bancassurance Group / Treasury / Investment Risk",
             why_test="Swedish bancassurance group with treasury and investment/market-risk functions tied to FX, rates, and portfolio risk.",
             career_url="https://jobb.lansforsakringar.se/", source_strategy="Job portal filtered by Treasury/Risk/Finance"),
        dict(canonical_company_id="baloise-group", company="Baloise Group", region="Switzerland", locations="Basel",
             archetype="Insurance / Investment & Treasury Risk",
             why_test="Swiss insurer with sizable investment portfolio requiring market-risk, ALM, and treasury expertise.",
             career_url="https://www.baloise.com/en/jobs.html", source_strategy="Careers site filtered by function"),
        dict(canonical_company_id="aareal-bank", company="Aareal Bank", region="Germany", locations="Wiesbaden",
             archetype="Commercial Real Estate Bank / Treasury / Financial Risk",
             why_test="Specialist CRE and structured finance bank with strong treasury, funding, derivatives and market-risk needs.",
             career_url="https://www.aareal-bank.com/en/your-perspectives-at-aareal-bank/jobs", source_strategy="Careers/jobs pages + LinkedIn"),
        dict(canonical_company_id="oberbank", company="Oberbank", region="Austria", locations="Linz; Vienna",
             archetype="Regional Universal Bank / Treasury / Risk",
             why_test="Independent Austrian regional universal bank with corporate banking, treasury, and market-risk functions.",
             career_url="https://www.oberbank.at/karriere", source_strategy="Karriere page + karriere.at listings"),
        dict(canonical_company_id="aktia-bank", company="Aktia Bank", region="Finland", locations="Helsinki",
             archetype="Banking & Asset Management / Treasury / Risk",
             why_test="Finnish bank and asset manager with treasury, balance-sheet management, and investment-risk roles.",
             career_url="https://www.aktia.com/en/careers", source_strategy="Careers page + LinkedIn"),
    ]),
    ("company_universe_wave2_holdings.csv", "Holding & Conglomerate", [
        dict(canonical_company_id="aker-asa", company="Aker ASA", region="Norway", locations="Oslo",
             archetype="Industrial Investment Holding Conglomerate",
             why_test="Publicly listed Norwegian industrial holding company with its own group treasury function and an active portfolio-finance/investment team.",
             career_url="", source_strategy="Monitor akerasa.com and LinkedIn; also check portfolio companies individually"),
        dict(canonical_company_id="ahlstrom-capital", company="Ahlström Capital Oy", region="Finland", locations="Helsinki",
             archetype="Family Investment Company / Holding",
             why_test="Multi-generation Finnish family office managing a diversified industrial and financial asset portfolio, needing investment/corporate-development/treasury talent.",
             career_url="https://ahlstromcapital.com/careers/", source_strategy="Own careers page"),
        dict(canonical_company_id="kirkbi", company="KIRKBI A/S", region="Denmark", locations="Billund",
             archetype="Family Holding Company / Investment Group",
             why_test="LEGO family holding company running a large diversified investment portfolio, needing group treasury, portfolio finance and risk/valuation professionals.",
             career_url="https://www.kirkbi.com/", source_strategy="Watch LinkedIn + kirkbi.com news section"),
        dict(canonical_company_id="franz-haniel-cie", company="Franz Haniel & Cie. GmbH", region="Germany", locations="Duisburg",
             archetype="Family Equity Holding / Diversified Conglomerate",
             why_test="One of Europe's oldest family-equity holding companies, offering corporate-development, group-treasury, and portfolio-finance roles.",
             career_url="https://www.haniel.de/en/careers/", source_strategy="Own careers portal"),
        dict(canonical_company_id="bc-industrieholding", company="B&C Industrieholding GmbH", region="Austria", locations="Vienna",
             archetype="Private-Foundation Industrial Holding",
             why_test="Privately-owned Austrian industrial holding requiring investment, corporate-development, and treasury expertise for portfolio management.",
             career_url="", source_strategy="Monitor bcgruppe.at and recruiting partner Skills Group"),
        dict(canonical_company_id="3i-group", company="3i Group plc", region="United Kingdom", locations="London",
             archetype="Listed Investment Company / Private Equity Holding",
             why_test="FTSE-listed international investment company running PE/infrastructure portfolios, hiring for portfolio finance, corporate development and valuation roles.",
             career_url="https://www.3i.com/about-us/careers/", source_strategy="Own careers page"),
    ]),
    ("company_universe_wave2_investment.csv", "Private Equity & Asset Management", [
        dict(canonical_company_id="ik-partners", company="IK Partners", region="Multi-region", locations="Stockholm; London",
             archetype="Private Equity / Buyout",
             why_test="Pan-European mid-market PE firm with strong Nordic and UK roots, relevant for investment/valuation and portfolio finance roles.",
             career_url="https://ikpartners.com/careers/", source_strategy="Own careers page"),
        dict(canonical_company_id="capman", company="CapMan", region="Nordics", locations="Helsinki; Stockholm; Copenhagen",
             archetype="Private Equity / Private Markets Asset Management",
             why_test="Listed Nordic private-markets manager (PE, real estate, infra) with treasury, portfolio valuation and risk functions across Finland/Sweden/Denmark.",
             career_url="https://capman.com/about-us/careers/", source_strategy="Own careers page"),
        dict(canonical_company_id="adelis-equity-partners", company="Adelis Equity Partners", region="Nordics",
             locations="Stockholm; Oslo; Copenhagen; Helsinki",
             archetype="Private Equity / Buyout",
             why_test="Nordic-focused mid-market PE firm active in Sweden, Norway, Denmark and Finland, fitting the target-market geography closely.",
             career_url="", source_strategy="No verified careers URL yet; check LinkedIn"),
        dict(canonical_company_id="pemberton-asset-management", company="Pemberton Asset Management", region="United Kingdom",
             locations="London",
             archetype="Private Credit / Direct Lending",
             why_test="Private-debt specialist (direct lending, NAV financing) needing credit risk, valuation and treasury-style portfolio finance skills.",
             career_url="https://pembertonam.com/careers/", source_strategy="Own careers page"),
        dict(canonical_company_id="golding-capital-partners", company="Golding Capital Partners", region="Germany", locations="Munich",
             archetype="Private Markets Fund-of-Funds / Asset Management",
             why_test="German independent private-markets asset manager offering investment, risk and portfolio-valuation roles in the DACH region.",
             career_url="https://www.goldingcapital.com/en/careers", source_strategy="Careers page links to recruiting.goldingcapital.com"),
        dict(canonical_company_id="coller-capital", company="Coller Capital", region="United Kingdom", locations="London",
             archetype="Private Equity Secondaries",
             why_test="Leading secondaries investor requiring deep valuation, portfolio analytics and risk-assessment expertise on PE fund stakes.",
             career_url="https://www.collercapital.com/careers/", source_strategy="Teamtailor ATS"),
        dict(canonical_company_id="astorg", company="Astorg", region="Multi-region", locations="London; Luxembourg; Paris; Frankfurt",
             archetype="Private Equity / Buyout",
             why_test="European upper-mid-market PE firm with a London office and continental footprint including Germany.",
             career_url="https://astorg.pinpointhq.com/", source_strategy="Pinpoint ATS"),
    ]),
    ("company_universe_wave3_investment.csv", "Investment Banking", [
        dict(canonical_company_id="berenberg", company="Berenberg", region="Multi-region", locations="Hamburg; Frankfurt; London",
             archetype="Investment Bank / M&A Advisory Boutique",
             why_test="German merchant bank with a growing investment banking / capital markets and corporate finance advisory arm in Germany and the UK.",
             career_url="https://careers.berenberg.com/", source_strategy="Own careers portal"),
        dict(canonical_company_id="carnegie-investment-bank", company="Carnegie Investment Bank", region="Nordics",
             locations="Stockholm; Copenhagen; Oslo; Helsinki",
             archetype="Investment Bank / M&A Advisory (Nordic)",
             why_test="Leading independent Nordic investment bank offering M&A advisory, ECM and corporate finance roles across Sweden, Denmark, Norway and Finland.",
             career_url="https://jobs.carnegie.se/", source_strategy="Own jobs portal"),
        dict(canonical_company_id="abg-sundal-collier", company="ABG Sundal Collier", region="Nordics",
             locations="Oslo; Stockholm; Copenhagen; Helsinki",
             archetype="Investment Bank / M&A Advisory Boutique (Nordic)",
             why_test="Independent Nordic investment bank focused on ECM, M&A and corporate finance advisory.",
             career_url="https://abgsc.teamtailor.com/jobs", source_strategy="Teamtailor ATS"),
    ]),
    ("company_universe_wave3_investment.csv", "Public Markets & Asset Management", [
        dict(canonical_company_id="ubs-asset-management", company="UBS Asset Management", region="Multi-region",
             locations="Zurich; Frankfurt; London; Vienna; Stockholm",
             archetype="Public Markets / Asset Management",
             why_test="Swiss-headquartered global asset manager with sizeable fixed income, multi-asset and risk functions across Switzerland, Germany and the UK.",
             career_url="https://www.ubs.com/global/en/assetmanagement/about/careers.html", source_strategy="UBS global careers site, Asset Management division"),
        dict(canonical_company_id="allianz-global-investors", company="Allianz Global Investors", region="Multi-region",
             locations="Frankfurt; Munich; Vienna; Zurich; London; Stockholm",
             archetype="Public Markets / Asset Management",
             why_test="Germany-based active manager with strong fixed income, credit and multi-asset/risk teams across DACH and Nordic offices.",
             career_url="https://www.allianzgi.com/en/our-firm/career", source_strategy="AllianzGI career site + careers.allianz.com"),
        dict(canonical_company_id="lgim", company="Legal & General Investment Management", region="United Kingdom",
             locations="London",
             archetype="Public Markets / Asset Management",
             why_test="One of Europe's largest institutional asset managers with major fixed income, LDI, derivatives overlay and risk teams in London.",
             career_url="https://careers.legalandgeneral.com/asset-management", source_strategy="Legal & General Group careers site, Asset Management area"),
        dict(canonical_company_id="nordea-asset-management", company="Nordea Asset Management", region="Multi-region",
             locations="Copenhagen; Helsinki; Oslo; Stockholm",
             archetype="Public Markets / Asset Management",
             why_test="Leading Nordic asset manager (part of Nordea Group) with cross-border fixed income, multi-asset and risk functions.",
             career_url="https://www.nordeaassetmanagement.com/careers/", source_strategy="Own careers page + Nordea Group careers site"),
        dict(canonical_company_id="erste-asset-management", company="Erste Asset Management", region="Multi-region",
             locations="Vienna; Prague",
             archetype="Public Markets / Asset Management",
             why_test="Austrian asset manager (Erste Group) with a strong CEE footprint including a Czech subsidiary, spanning Czechia and Austria target markets.",
             career_url="https://www.erste-am.com/en/about/who-we-are/career", source_strategy="Own career page + Erste Group careers portal"),
    ]),
    ("company_universe_wave3_investment.csv", "Specialist & Boutique Funds", [
        dict(canonical_company_id="nordkinn-asset-management", company="Nordkinn Asset Management", region="Nordics",
             locations="Stockholm; Oslo",
             archetype="Macro / Fixed Income Hedge Fund",
             why_test="Nordic-focused fixed income macro hedge fund trading rates and FX directly matching treasury, interest rates and FX background.",
             career_url="", source_strategy="No dedicated jobs page found; monitor LinkedIn"),
        dict(canonical_company_id="lynx-asset-management", company="Lynx Asset Management", region="Sweden", locations="Stockholm",
             archetype="Quant Fund / Systematic Trading (CTA)",
             why_test="Systematic trading firm running quantitative strategies across rates, FX and commodities futures, well suited to a Python/derivatives-minded profile.",
             career_url="https://careers.lynxhedge.se/jobs", source_strategy="Own careers portal"),
        dict(canonical_company_id="quoniam-asset-management", company="Quoniam Asset Management", region="Multi-region",
             locations="Frankfurt; London",
             archetype="Quant Fund / Systematic Asset Manager",
             why_test="Quantitative asset manager using factor and risk models across equities/fixed income, fitting valuation, risk and quant/Python skill set.",
             career_url="https://www.quoniam.com/en/careers/", source_strategy="Own careers page"),
        dict(canonical_company_id="lupus-alpha-asset-management", company="Lupus alpha Asset Management", region="Germany",
             locations="Frankfurt am Main",
             archetype="Derivatives-Based Boutique Asset Manager",
             why_test="Specialist built entirely around derivatives and volatility strategies, directly aligned with derivatives and valuation expertise.",
             career_url="https://www.lupusalpha.com/careers/", source_strategy="Own careers page + German job boards"),
        dict(canonical_company_id="systematica-investments", company="Systematica Investments", region="Multi-region",
             locations="Lugano; London",
             archetype="Quant Fund / Systematic Macro Trading",
             why_test="Large systematic macro/trend-following manager trading rates, FX and commodities futures.",
             career_url="https://systematica.pinpointhq.com/", source_strategy="Pinpoint ATS"),
        dict(canonical_company_id="gam-investments", company="GAM Investments", region="Multi-region",
             locations="Zurich; London",
             archetype="Boutique Active/Absolute Return Asset Manager",
             why_test="Independent Swiss-headquartered asset manager with systematic and absolute-return/multi-asset strategies.",
             career_url="https://www.gam.com/en/careers", source_strategy="Own careers page + LinkedIn"),
    ]),
]


def main() -> None:
    skipped_duplicates: list[str] = []
    added_total = 0
    by_file: dict[str, list[dict]] = {}
    for wave_file, category, rows in BATCHES:
        by_file.setdefault(wave_file, [])
        for row in rows:
            if row["canonical_company_id"] in EXISTING_IDS:
                skipped_duplicates.append(f"{row['canonical_company_id']} ({category})")
                continue
            full_row = {col: "" for col in UNIVERSE_COLUMNS}
            full_row.update(row)
            full_row["company_category"] = category
            full_row["rating"] = "Unrated"
            by_file[wave_file].append(full_row)

    for wave_file, new_rows in by_file.items():
        if not new_rows:
            continue
        path = DATA / wave_file
        existing_df = pd.read_csv(path).fillna("")
        new_df = pd.DataFrame(new_rows)[UNIVERSE_COLUMNS]
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="canonical_company_id", keep="first")
        combined.to_csv(path, index=False)
        added_total += len(new_df)
        print(f"{wave_file}: +{len(new_df)} new companies (now {len(combined)} total)")

    if skipped_duplicates:
        print(f"\nSkipped {len(skipped_duplicates)} already-known companies: {', '.join(skipped_duplicates)}")
    print(f"\nTotal newly added: {added_total}")


if __name__ == "__main__":
    main()
