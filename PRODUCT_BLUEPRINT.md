# Professional Dashboard / Opportunity Radar — Product Blueprint

## Purpose

Professional Dashboard is a personal opportunity intelligence system. Its primary use case is continuous sourcing of relevant **full-time jobs** with less manual searching. Over time, it should also discover and manage broader professional opportunities: tenders, consulting and freelance work, expert calls, company signals, collaborations, and self-directed ideas or projects.

The product should answer one practical question: **Which professional opportunities deserve my attention now, and what should I do next?**

## Core operating model

```text
SOURCES → DISCOVERY → OPPORTUNITY INBOX → REVIEW → ACTIVE → OUTCOME
```

- **Sources** are websites, APIs, feeds, career pages, newsletters, alerts, or manual inputs.
- **Discovery** fetches, extracts, normalizes, deduplicates, and enriches potential opportunities.
- **Opportunity Inbox** is the unreviewed stream of newly found items.
- **Review** is a fast human decision: `Interested`, `Maybe`, or `Pass`, optionally with a reason and note.
- **Active** contains opportunities being pursued, such as researching, applying, interviewing, contacting, bidding, or following up.
- **Outcome** records the result and closes the learning loop.

The system supports decision-making; it does not make final career decisions automatically.

## Primary use case: full-time job sourcing

Jobs are the first product wedge. Job sourcing is modelled as:

```text
WHAT × WHERE × WHO × SOURCE
```

- **WHAT** — target roles, functions, seniority, keywords, skills, industries, and exclusions.
- **WHERE** — geography, remote/hybrid/on-site preference, countries, cities, and time zones.
- **WHO** — target companies, company types, size/stage, sectors, and hiring signals.
- **SOURCE** — job boards, professional networks, ATS/career pages, recruiters, aggregators, newsletters, referrals, and saved searches.

This makes searches explicit, composable, and debuggable. A poor result should be traceable to a profile assumption, company universe, source, query, extraction issue, or freshness problem.

## Company Universe and Company Radar

The **Company Universe** is the maintained set of companies worth monitoring, independent of whether they have an open role today. Companies may come from target lists, discoveries, manual additions, or later from signals and recommendations.

Each company can carry sector, geography, stage/size, priority, career-page URL, notes, and monitoring status. The system should monitor career pages and related sources to surface new or changed openings.

**Company Radar** turns companies into an ongoing discovery channel. It should detect relevant hiring activity and career-page changes, and eventually other company-level signals. It may surface both explicit vacancies and reasons to investigate a company.

### Group, entity, and source identity

Multinational groups must not create duplicate companies or duplicate opportunities. The model distinguishes:

- **Company** — the canonical group or standalone employer used for rating and monitoring.
- **CompanyEntity** — a local legal entity, subsidiary, brand, or business unit linked to its canonical parent.
- **CompanyAlias** — alternate names, abbreviations, domains, and ATS employer names used for identity resolution.
- **Source** — each global career portal, country portal, subsidiary portal, ATS tenant, or external board.
- **OpportunitySource** — an observation linking one canonical Opportunity to every source where it was found.

A global careers page and its local country pages therefore remain separate Sources but roll up to one Company. Opportunity deduplication should prefer stable requisition IDs and canonical URLs, then use a fingerprint based on canonical company, normalized title, location cluster, and description similarity. Merging must preserve all source URLs plus `first_seen` and `last_seen` timestamps.

## Feedback-driven calibration

The review actions `Interested`, `Maybe`, and `Pass` are product data, not merely labels.

- A `Pass` should capture a useful reason: role mismatch, location, seniority, company, compensation, contract type, stale listing, duplicate, or other.
- Feedback should reveal which combinations of role, company, geography, and source work.
- Later, feedback can improve ranking, source selection, query generation, and `SearchProfile` calibration.

Do **not** build sophisticated scoring before collecting real feedback. Early scoring should be transparent and lightweight, supporting review order rather than claiming precision. Later, a low score must **not** mean hard exclusion: the system needs exploration, including unfamiliar companies, adjacent roles, and weak-signal opportunities.

## Sourcing engines

The platform has a shared source/discovery framework with several engines:

1. **Jobs** — full-time roles; the first production-quality sourcing flow.
2. **Tenders** — public and private procurement or RFP opportunities.
3. **Consulting / Freelance** — contract, fractional, project, and independent work.
4. **Expert** — expert-network calls, advisory, board, mentoring, speaking, and specialist work.
5. **Company Radar** — monitored target companies, career pages, and company signals.
6. **Experimental** — uncertain or niche discovery channels tested without distorting the core product.

Engines share common opportunity objects and review mechanics while retaining domain-specific fields and sourcing logic.

## Main app hierarchy

- **Dashboard**
  - **Home** — daily briefing: new items, review queue, active next steps, and notable radar signals.
- **Opportunities**
  - **Overview** — unified inbox and searchable catalogue across opportunity types.
  - **Jobs** — job-specific discovery, filters, profiles, searches, and review workflow.
  - **Companies** — Company Universe, company records, career-page monitoring, and company insights.
- **Workspace**
  - **Pipeline** — active pursuits, stages, tasks, deadlines, and outcomes.
  - **Ideas & Projects** — self-created opportunities, experiments, collaborations, and projects.
- **System**
  - **Sources / Radar** — sources, health/freshness, search runs, monitoring, and discovery diagnostics.

## Core objects

### Opportunity

A normalized item discovered or manually created. It includes type, title, company/organization, description, URL, source, timestamps, location/remote data, status, review decision, notes, tags, and pipeline links. Source-specific raw data is retained where useful.

### Company

An organization in the Company Universe or referenced by an opportunity. It includes identity, a broad `CompanyCategory`, a more specific archetype, metadata, priority, career/source URLs, monitoring configuration, notes, and opportunity relationships. The initial categories are `Consulting`, `Banking & Financial Services`, `Private Equity & Asset Management`, `Corporate`, and `Holding & Conglomerate`. Category belongs to the canonical company, not to each local career-page source.

### Source

A configured discovery input: provider, career page, feed, query, integration, or manual import. It records scope, engine, cadence, reliability, run history, freshness, and failure state.

### SearchProfile

A reusable definition of desired opportunities. For jobs it expresses `WHAT × WHERE × WHO × SOURCE`, including inclusions and exclusions. Profiles evolve from explicit preferences and observed review feedback.

## Product principles

- **Build for iteration, not completeness.** Prefer a usable learning loop over a broad but inert platform.
- **Human review is central.** Automation reduces searching and organizing; the user keeps judgment and control.
- **One shared lifecycle, domain-specific discovery.** Different opportunity types can enter one Inbox and Pipeline without identical data models.
- **Traceability matters.** Every result should show why it appeared and where it came from.
- **Freshness, deduplication, and reliability are first-class.** The system fails if it is stale, noisy, or opaque.
- **Exploration is intentional.** Optimize relevance without narrowing the opportunity space too early.

## v0 roadmap

v0 validates the full learning loop around jobs rather than simulating a complete platform.

1. **App shell** — navigation for the main sections and a job-focused default experience.
2. **Persistence** — durable storage for Opportunities, Companies, Sources, SearchProfiles, reviews, pipeline states, and notes.
3. **Source framework** — a minimal extensible model for sources, runs, normalized results, deduplication, and freshness/error visibility.
4. **First real sourcing** — connect at least one real job source or monitored career-page flow and ingest listings into the Inbox.
5. **Review and pipeline loop** — support `Interested` / `Maybe` / `Pass`, reasons, notes, active stages, and outcomes.
6. **Company Universe baseline** — manually add and monitor target companies, including career-page URLs.

Only after real usage should the product prioritize richer ranking, automatic search calibration, additional engines, dashboards, and advanced integrations.
