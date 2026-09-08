# Alternative Signals Playbook

Use public web evidence to discover differentiated equity ideas. Alternative data generates hypotheses; it never bypasses fundamental, bear-case, Saxo identity, quote, liquidity, or risk review.

## Signal families

Search across genuinely different families rather than repeating variations of the same news query:

- Ownership and capital allocation: clustered open-market insider buying, activist 13D filings, changes in institutional ownership, buybacks, dilution, refinancing, auditor changes, and late filings.
- Commercial traction: newly awarded public contracts, tender results, customer wins, product availability or pricing changes, hiring-pattern changes, and supplier/customer read-throughs.
- Scientific and regulatory: clinical-trial status or endpoint changes, FDA decisions, patent/exclusivity events, permits, recalls, and enforcement actions.
- Physical economy: energy production and inventories, power demand, commodity balances, freight/port/aviation activity, weather-linked demand, and supply-chain bottlenecks.
- Positioning and market structure: short-interest changes, futures positioning, ETF flows, unusual volume, gap-and-reversal behavior, and options activity. Options or short data may inform a thesis but remain non-executable and must not be confused with confirmed informed trading.
- Attention and diffusion: search interest, app rankings, web traffic, developer activity, job postings, specialist publications, and local-language reporting. Treat attention data as noisy and manipulable; it cannot support a trade without independent evidence.

Do not impose a candidate quota or stop after one familiar security. Continue into another family while the marginal search is producing new issuer mappings or thesis-changing evidence.

## Preferred public sources

Start with primary, time-stamped sources and use secondary sources to locate—not replace—the underlying record:

- SEC EDGAR submissions and XBRL APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Issuer investor-relations pages, exchange announcements, national regulators, and official gazettes.
- USAspending award search/API: https://api.usaspending.gov/docs/endpoints
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-about-studies/learn-about-api
- FDA/openFDA datasets: https://open.fda.gov/data/drugsfda/
- FINRA equity short interest: https://www.finra.org/finra-data/browse-catalog/equity-short-interest
- CFTC Commitments of Traders: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- EIA open energy data: https://www.eia.gov/opendata/
- FRED economic data: https://fred.stlouisfed.org/docs/api/fred/overview.html
- Google Trends: https://trends.google.com/explore

Respect source access rules and rate limits. Never save API keys, cookies, paywalled text, raw responses, or personal data in run artifacts. If a source requires a credential that is not already configured, skip it and record the coverage gap.

## Signal card

Record every promoted signal in `agent/state/signals.json` and the current run research with:

- `observed_at`, `source_published_at`, source URL, and known publication/reporting lag;
- the raw observation expressed as a measurable change against a prior baseline;
- exact issuer/security mapping and the economic transmission mechanism;
- freshness, surprise, persistence, and confidence assessments;
- at least one independent confirming evidence type, including one primary source;
- plausible benign explanation, manipulation risk, crowding risk, and disconfirming evidence;
- catalyst horizon, invalidation condition, and expiry/recheck time;
- status such as `new`, `confirmed`, `weakening`, `expired`, or `rejected`.

Distinguish the observation date from when the market could first know it. Reject signals that depend on look-ahead, stale publication, ambiguous issuer mapping, private/material non-public information, or an unrepeatable screenshot. Avoid double-counting correlated signals and do not treat daily short-sale volume as short interest.

## Promotion gate

Promote a signal to bull/bear review only when the economic link to a Saxo-resolvable equity is explicit and the evidence could plausibly change a portfolio decision. Prefer a modest company-specific position over broad beta only when the signal survives independent confirmation, fundamentals, valuation, liquidity, and the bear review. A no-trade result remains valid.
