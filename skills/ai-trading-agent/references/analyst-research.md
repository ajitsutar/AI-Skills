# Analyst research, targets and source discovery

Use this procedure when stock analysis calls for analyst evidence, consensus price
targets, estimate revisions or the record of a research author. It supplements
primary financial and business review. Analyst opinions are neither verified
company facts nor a calibrated forecast of the investment's return.

For comparisons across recommendations, bind each displayed forward P/E to the
actual EPS fiscal period, adjusted or statutory basis, currency, estimate vintage
and quote timestamp. Next fiscal year is not automatically next twelve months.
PEG needs its earnings-growth definition and horizon; a low vendor PEG alone does
not establish intrinsic undervaluation. Keep currency-neutral growth distinct from
reported-currency growth, and do not use a single historical quarter as forecast
EPS CAGR. Banks require credit, capital and funding review rather than an industrial
CFO/EV formula. A provider's missing specialized bank inputs is a coverage gap.

For explicit structured records, [run and report](run-and-report.md#analyst-evidence)
executes the existing evidence helper and renders separate cohorts, exclusions and
source pointers. It does not acquire missing reports or pool provider estimates.

## Discover sources for the actual issuer

Build a dated source map for each issuer advanced to this review. Identify the
legal entity, exchange, share class, CIK where applicable, trading currency and
ADR ratio before matching names or targets. A whole-market discovery screen does
not mean every listed company's analyst reports were read: report these coverage
counts separately.

1. Open the issuer's investor-relations site, releases, presentations and relevant
   filings. Identify the latest results, subsequent guidance or preannouncement,
   and known covering firms. An issuer's analyst-coverage list identifies possible
   sources; it does not supply their current recommendations.
2. Search with the exact issuer name, ticker/exchange, relevant dates and terms such
   as `research report`, `price target`, `upgrade`, `downgrade`, `estimate revision`,
   `earnings outlook` and `investment risks`. Follow original firm/author reports
   where publicly available; seek a credible opposing thesis as well as favorable
   coverage. Do not select sources because they support a desired pick.
3. Discover appropriate provider pages dynamically. Yahoo Finance, Morningstar,
   Motley Fool, MSN Money, Bloomberg, WSJ, Reuters, MarketWatch, Nasdaq, TipRanks,
   brokerage research and sector publications are possible routes, not a fixed
   required list or a claim of access. Add newly found relevant sources to the map.
   A site name, search result or index page is not evidence that its report was read.
4. Open the exact report/page and retain its successfully opened final URL. Record
   its actual access, publication/update time,
   author, original firm and underlying data provider. Follow syndication to the
   original report when possible. Search snippets remain discovery evidence.
5. Continue until the declared search budget is exhausted or the required source
   categories have been attempted and additional searches repeat existing evidence.
   Save attempted queries, date window, pages examined, gaps and stopping reason.
   Increase the budget for a material unresolved conflict; do not manufacture a
   consensus to fill missing coverage.

This is a bounded agent research workflow, not a bundled universal website scraper.
Use available read-only web tools or documented provider APIs. Follow current site
terms, rate limits and access controls. Public access to one article does not grant
bulk access, full historical coverage or redistribution rights. An inaccessible
report stays unavailable; never bypass a paywall or human check. No new paid
service, account or authentication transfer is implied by this workflow.

Maintain an investment-information coverage matrix: prices/volume/corporate actions;
reported financials and business segments; valuation and growth assumptions;
management guidance and analyst forecasts; target/rating/estimate revisions;
earnings and other catalysts; balance-sheet/refinancing risks; competitive,
regulatory and litigation developments; distributions/buybacks; insider and
institutional ownership; and short/borrow/options data where relevant and accessible.
Record each field's period, units, observation age and source lineage. Delayed 13F
holdings or settlement-date short interest are not live positioning; apparent
options flow does not identify the investor's net direction. Irrelevant or missing
fields remain explicit, rather than collecting every website for its own sake.
A dated borrow fee is a cost observation; it does not establish current locate,
inventory availability or recall status. Describing a fee as normal or high
requires a sourced comparison basis.

## Keep a coverage and evidence ledger

For every attempted source retain issuer, query/topic, URL, original publisher,
underlying firm/analyst when known, publication time, observation time, source/data
provider, access status, usable fields and unresolved conflicts. Use distinctions
such as `FULL_REPORT`, `ATTRIBUTED_EXCERPT`, `SNIPPET_ONLY`, `PAYWALL`,
`AUTH_REQUIRED`, `ACCESS_DENIED`, `FAILED`, `NO_RELEVANT_RESULT` or `NOT_ATTEMPTED`.
Use `NO_RELEVANT_RESULT` only for a completed query with a retained response or
receipt supporting that result and its search scope. A planned query or one that
could not be issued because tools or access were unavailable is `NOT_ATTEMPTED`;
record the reason separately.

Bind each dependence claim to its source population and named entities. Two
aggregate consensus publishers declaring a common upstream provider supports that
publisher-lineage observation only. It does not establish that their constituent
research firms share an upstream provider, data or research assumptions. Missing
individual-firm lineage stays unknown even when the provider lists those firms in
its population. A conditional statement that research firms may share inputs is
different from an observed common-input claim; neither establishes statistical
independence or a calibrated target-attainment probability.

The existing analyst helper returns `source_population_provenance` separately for
included individual-target firms and aggregate providers, including their declared
lineage, any common-upstream groups, and an `UNESTABLISHED` statistical-independence
status. The analyst report projects these population-specific fields into retained
facts. Do not move a lineage relation from one population into another in prose.
The legacy `independent_firms` numerical field counts distinct firm identities
after deduplication; it is not an independence test. Its meaning is explicitly
retained in `consensus.firm_count_meaning`.

A readable article quoting a target supports that attributed target, not a claim
to have read the underlying research report. A headline without an attributable
analyst and firm cannot enter the independently constructed consensus. Reposts of
one firm's call across Yahoo, MSN and a wire count as one opinion. Distinguish a
sell-side analyst, independent research analyst, journalist, blogger, newsletter
author and subscription-service portfolio. Their ratings and performance records
are not interchangeable.

Keep source material in a separate local runtime directory where retention is
permitted. Save a short supporting excerpt and locator with the URL, timestamps
and content hash. Retain PDF originals and extraction provenance when converting
permitted PDF evidence to UTF-8 text for the helper. Do not put copyrighted reports,
personal broker research or authenticated material in a public skill repository.
An evidence hash proves byte consistency, not publisher authenticity or accurate
interpretation; the reviewer must verify attribution, numbers and definitions.

## Forward targets and consensus

Interpret the user's requested forward target separately from the backward-looking
52-week trading high/low. The executable helper supports explicit
`forward_12_months` and `forward_52_weeks` cohorts. They are separate contracts;
calendar months and 364 days are not automatically identical. Unknown, fiscal-year
and other horizon targets need their own review and must not be silently relabeled.
Never scale a twelve-month target into a one-month expected return.

For each usable target record the actual recommendation issue date, original
firm/analyst, rating scale, target currency, share/split basis, horizon, previous
target when verified, and report access. A fresh news recap does not refresh an
old recommendation. Match the target with the quoted share class and ADR ratio;
resolve splits and currency differences explicitly before calculation. Use the
original rating date for staleness decisions. The helper requires `issued_at`,
uses it for staleness and latest-firm selection, and rejects an issue time after
the supporting source's publication. Reviewers must not substitute a recap's new
publication timestamp for the original target date.

The observed-cohort calculation uses the latest admissible target per independent
firm. Same-time conflicting targets remain unresolved. It reports firm count,
mean, median, minimum, maximum, linearly interpolated quartiles and
`(Q3 - Q1) / median`. A single observation is not broad consensus, and a narrow
observed range does not establish low uncertainty. Analysts can share assumptions,
data and incentives, so firm count is not an independent statistical sample size.

Provider-reported consensus is a separate observation: retain its date, constituent
count, statistic, target horizon and methodology where available. Never average
Yahoo's, MSN's and another site's averages into a new consensus; their populations
may overlap. Distinguish the helper's partial observed cohort from a provider's
larger pool. Investigate material differences in coverage, freshness, basis and
statistic instead of selecting the highest target.
Observed pool differences are facts; their proposed explanation of a numerical
discrepancy remains a hypothesis. Call the discrepancy reconciled only when
compatible constituent values, vintages and methodology reproduce it. Otherwise
retain the unresolved discrepancy alongside the known differences.

If a verified quote on the same currency/share basis is supplied, the helper
calculates `(median target / price - 1) * 100`. This is implied price change to the
target, excluding dividends, costs and probability of attainment. Show the quote
timestamp; it is not a live executable quote merely because the calculation ran.
The configurable `max_quote_age_hours` defaults to 96 for research (including
weekends), not order execution. Older quotes return `STALE` and no implied-upside
number; use the actual market calendar and broker's quote checks for an order.

Review changes in targets, EPS/revenue estimates and ratings separately. For a
revision trend, compare frozen observations with matched firm, issuer, fiscal
period, metric, currency and accounting basis. Report additions/drops in coverage
and the fraction of comparable observations. The current helper does not calculate
an estimate-revision signal or automatically extract historical revisions.
Keep each attribute attached to its actual metric: an EPS forecast's fiscal year,
GAAP/adjusted label and diluted-share definition do not establish the horizon or
share basis of an adjacent price target. A record containing both needs separate
metadata for each; do not describe a price target as adjusted EPS or infer its
expiry from the EPS fiscal year.

Morningstar intrinsic fair value belongs in a separate valuation field, not a
forward-price-target pool; its published methodology distinguishes those concepts.
Record moat, uncertainty and star-rating definitions alongside the estimate.
[Morningstar equity methodology](https://www.morningstar.in/docs/methodology/equitiesresearchmethodology.pdf).

When comparing fair value, forward targets and a past trading range, retain each
item's own currency, share class and split/adjustment basis. Do not inherit those
fields from the best-documented neighboring record. Before cross-item ratios or
range-position calculations, run `evidence.operand_compatibility` for the required
issuer/security, currency and share-basis dimensions. Missing metadata remains
unknown. The conceptual comparison can proceed; numerical cross-item results need
a compatible basis or a separately labeled conditional same-basis assumption.
An evidence-consistent excerpt does not prove that the DCF was independently
reproduced or that the historical price series was checked. Keep those coverage
claims separate from the arithmetic.

Use `evidence.price_comparison` for cross-item percentage arithmetic. Its
arguments are `quote`, `references` and optional `conditional_same_basis`.
Each operand has a unique `id`, a positive numeric `value`, and its own flat
`security_id`, `issuer_id`, `currency`, `share_basis` and `adjustment_basis`
metadata. Each reference also has `kind`: `fair_value`, `forward_target`,
`historical_high` or `historical_low`. Preserve missing fields; do not copy
neighboring metadata. This helper checks all five dimensions and returns an
unresolved primary calculation when any required basis is missing or conflicting.

It always distinguishes two directions and denominators:

- `quote_discount_relative_to_reference_pct` uses
  `100 * (reference - quote) / reference`. Relative to a past high this means
  percent below that high; negative values mean above the reference.
- `price_change_from_quote_to_reference_pct` uses
  `100 * (reference - quote) / quote`. This means appreciation needed from the
  quote to the reference; negative values mean a decline. It cannot be described
  as the quote's percentage discount to the reference.

Each computed field retains the formula, denominator operand ID, denominator
value and meaning. Retain those fields when composing the answer. Optional
`conditional_same_basis` has exactly `label` and `dimensions`, the latter an
object with explicit assumed values for missing dimensions. The separate
conditional sensitivity can fill missing metadata but cannot reconcile known
conflicts or upgrade the original unknown primary basis. Arithmetic does not
establish expected returns, probabilities, independent DCF reproduction or
historical-series verification.

The analyst report envelope accepts optional `price_comparisons`, a list of these
exact helper argument objects alongside `cohorts` and `supplemental_evidence`.
It executes the typed helper and includes pointer-bound formulas, denominator
values, metadata gaps and conditional results in its report. Fair-value and
historical-range supplemental records retain explicit missing share/adjustment
basis even when no numeric comparison was requested.

## Analyst success rate and reputation

For any provider-reported performance number retain analyst identity, firm,
provider, evaluation start/end, recommendation count, holding/exit rule, benchmark,
return definition, success definition and methodology URL. Include source date,
sector coverage, gross/net and dividend treatment if available. Unknown fields
remain unknown. A profile's present firm is not necessarily the employer that
issued all past calls. Compare like evaluation windows and horizons; a one-year
stock-picking record does not establish intraday skill.

TipRanks describes a provider-specific measurement convention for recommendations,
including how changed ratings close prior calls. Save the actual selected profile
settings and current methodology; do not treat a displayed win rate as a probability
the next recommendation succeeds. [TipRanks methodology FAQ](https://www.tipranks.com/glossary/f/faq%26apos%3B).

Record professional role, verifiable sector experience, methodology transparency,
corrections and disclosed conflicts as qualitative evidence. A correction
establishes that something changed, not its impact; keep impact unknown unless
before/after values or a substantiated impact assessment support it. Firm prestige,
social followers, article count and favorable ratings do not establish forecasting
ability. Read compensation, ownership, investment-banking and sponsored-content
disclosures where supplied; FINRA's research rule describes several relevant
disclosure categories. It does not certify an individual recommendation's quality.
[FINRA Rule 2241](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2241).

An independently measured analyst-skill score would require a dated, sufficiently
complete historical recommendation ledger; executable entry/exit conventions;
total returns, costs and benchmark comparison; delistings and discontinued analysts;
and controls for overlap, sector exposures, sample size and selection bias. That
database and validation are not bundled. The helper labels track records as
provider-reported, never independently reproduced, and assigns no selection weight.
Do not infer success from a handful of visible winning calls or retroactively
filter the analyst set by today's best performers.

## Executable evidence review

From the installed skill directory, create the runtime parent outside the package:

```text
python scripts/analyst_evidence.py ../runtime/analyst-input.json ../runtime/sources ../runtime/analyst-result.json
```

The JSON request uses the following contract. All timestamps are timezone-aware;
all numeric values must be finite JSON numbers, not formatted strings.

| Field | Content |
|---|---|
| `as_of` | Information cutoff |
| `issuer`, `currency`, `price_basis`, `target_horizon` | Explicit common dimensions |
| `max_target_age_days` | Positive age limit; defaults to 90, a configurable research convention |
| `max_quote_age_hours` | Positive research quote age limit; defaults to 96 |
| `individual_targets` | Rows with `record_id`, common dimensions, `firm_id`, `analyst_id`, `issued_at`, positive `target`, `access`, `source` |
| `quote` | Optional matching `issuer`, `currency`, `price_basis`, positive `price`, `source` |
| `provider_consensus` | Separately sourced provider observations with dimensions and retained metadata |
| `analyst_track_records` | Sourced performance records with the definitions described above |
| `source_discovery` | Agent-supplied coverage ledger; preserved, not independently verified |

Each `source` includes `path` relative to the source root, `sha256`, HTTPS `url`,
`published_at`, `observed_at`, a `verbatim_excerpt` present in the saved UTF-8 bytes,
and a useful `locator`. Use only excerpts permitted for the source. The helper
rejects missing/changed bytes, paths outside the source root and future evidence.
Observation before publication and track-record outcomes after the supporting
source's publication are invalid chronologies. A missing success definition keeps
a success-rate record partial, even when a percentage is visible.
It does not fetch reports, authenticate their publisher or confirm every extracted
number appears with the claimed meaning. Review malformed records and exclusions;
do not turn an error into an empty favorable result.

Missing analyst evidence does not authorize replacing the shared factor profile.
News, guidance and analyst evidence can expose thesis risks and require further
review, but they do not silently add weights, rerank the official candidate queue,
establish calibrated Strong Buy labels. Findings inform recommendations and do
not authorize, veto or pause the common host handoff.
