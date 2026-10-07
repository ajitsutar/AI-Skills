# Stock discovery, comparable valuation and value-trap review

Use for broad stock discovery or a requested candidate comparison. This procedure
defines research, not trade permission. It does not download a constituent universe
or financial data automatically. Never claim a scan ran without its input/output.

For broad or ranked screens, read [research-run-methodology.md](research-run-methodology.md)
and record the run's mandate, snapshot, field/peer definitions, selection and ranking
rules before choosing the shortlist. Log later changes and judgment overrides.

## Configurable universe and honest coverage

Use the user's research universe. If none is supplied for broad U.S. discovery,
state S&P 500 as a provisional starting universe. It can be replaced with another
index, market, sector, watchlist or explicit security list. A request about existing
holdings need not trigger an index-wide scan. Research membership never changes
the trading policy's allowed_symbols.

Freeze the actual constituent security list, source, effective date, retrieval
time and ticker/share-class mappings. Do not hard-code 500 or 503 securities. The
[index provider describes 500 leading companies](https://www.spglobal.com/spdji/en/indices/equity/sp-500/);
use the dated constituent list for the actual security count. Historical testing
requires membership as known then, including removals, rather than today's survivors.

Record each security as screened/retained, screened/excluded (failed discovery
criterion), screened/not_advanced (not chosen for deeper work), or missing data.
Give the reason; not_advanced is not a failed investment thesis. Record absent rows
separately. A completed retrieval is not completed
analysis. Report initial coverage and deeper finalist reviews separately. If data
access prevents a complete scan, say "partial coverage" and give counts; do not
substitute a published value list and call it an index-wide screen.

Use [screen-review.md](../templates/screen-review.md) and, when a structured manifest
is available, `python scripts/screen_review.py path/to/screen.json`. The helper
checks declared coverage and statuses; it cannot authenticate a constituent list,
verify citations, perform valuation, fetch events or approve an order. The runnable
[fictional-screen.json](../examples/fictional-screen.json) illustrates its schema.

No fixed candidate count belongs in this skill. Return all candidates that merit
inclusion at the requested depth, which may be none; use a table/file for larger
results. Never fill a quota by weakening criteria. Rank only after classification.

## Comparable evidence before a cheapness score

Record currency, quote time, accounting period, publication date, source, units,
GAAP/non-GAAP basis, trailing/forward definition and estimate vintage. Pulling every
ticker in ten minutes improves quote comparability but does not synchronize the
underlying financial periods or forecast updates. Do not mix next-fiscal-year EPS
with next-twelve-month EPS without labeling the difference.

Start comparisons within a suitable industry/business model; use a sector median
as a broad reference when suitable peers are unavailable. Show peer membership,
metric denominator, count and exclusions. P/B across telecom, platforms and media
is not a uniform valuation test. Positive-EPS filters must be disclosed: they
exclude loss-making growth firms and change the comparison population. Construct
peer medians before selecting cheap finalists; explain outlier handling, negative
denominators, multiple share classes and small groups. No universal P/E/P/B cutoff.

| Business | Valuation and normalization checks |
|---|---|
| Ordinary profitable nonfinancial | Trailing and forward P/E, EV/operating earnings, cash conversion and FCF yield; reconcile exceptional items, capex, working capital, dilution and stock compensation |
| Banks/financial firms | P/tangible book with sustainable return on tangible equity, credit losses, funding, liquidity and regulatory capital; use equity-based cash/distribution capacity, not an industrial FCF or debt/EBITDA gate |
| Equity REITs | Reconciled FFO/AFFO per share, recurring property capex, occupancy/tenant risk, maturities and payout coverage; GAAP earnings remain visible; FFO is not cash flow and issuer AFFO adjustments need comparison |
| Energy/materials/cyclicals | Mid-cycle earnings/FCF, maintenance capex, realized commodity prices, hedges, volume/cost sensitivity and balance-sheet survival under a weaker price cycle |
| Loss-making growth/biotech | Revenue quality, unit economics, runway, dilution and probability/scenario assumptions; negative P/E/PEG is not "cheap" and an unproven profitability path is speculative |

Financial firms' funding and reinvestment definitions warrant different valuation
models ([Damodaran's financial-firm valuation paper](https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/finfirm09.pdf)).
For REIT FFO definitions use [Nareit's guidance](https://www.reit.com/nareit/advocacy/policy/nareit-ffo-white-paper-and-related-implementation)
and the issuer's reconciliation, rather than treating an aggregator multiple as audited.

## Normalization and value-trap test

For every finalist document these checks with evidence and an explicit conclusion:

1. **Earnings quality:** recurring operating earnings versus disposals, tax benefits,
   reserve releases, acquisition accounting and other exceptional items.
2. **Cash support:** earnings-to-cash bridge, maintenance/growth capex, working-capital
   reversals and dilution. For financials, use the sector-appropriate equivalent.
3. **Balance sheet:** debt maturity ladder, refinancing cost, covenants, liquidity,
   contingent liabilities and sector-specific capital/solvency risks.
4. **Cycle normalization:** multi-year results and plausible mid-cycle margins;
   peaks are not permanent and depressed profits do not automatically recover.
5. **Structural health:** competitive position, customer retention, demand changes,
   pricing power and evidence that deterioration is temporary versus persistent.
6. **Valuation and growth:** bear/base/bull ranges with per-share dilution, a
   defensible growth mechanism and what would falsify the thesis.
7. **Analyst evidence:** coverage quality, disagreement and revisions below. Analysts
   cannot substitute for missing filings or balance-sheet work.

Show a bridge from reported to normalized earnings/FCF with each adjustment's
source, recurrence and sensitivity. Keep management targets, consensus forecasts
and your modeled assumptions separate. For merger synergies, show gross versus net,
pre-tax versus after-tax, realization timing, remaining integration cash costs and
financing/dilution. A share price divided by forward P/E merely recovers implied
EPS; it does not independently confirm it. Model partial/delayed/no realization.
If this work cannot be done, classify the thesis as unresolved or speculative,
not verified normalization. Normalization must not routinely erase recurring costs.

## Analyst, commodity, insider and beta context

Use latest available same-horizon targets per analyst/firm, with dates, currency,
sample size, low/median/high and quartiles/IQR when individual observations exist.
Normalize dispersion (for example IQR/median) and explain the metric; do not call
a range "tight" by eye. Low/high/mean aggregates cannot reconstruct quartiles.
Show rating upgrades/downgrades, target changes and EPS/revenue estimate revisions
as separate series over declared comparable windows (for example 30/90 days).
Deduplicate firms and show initiations, coverage changes and stale observations.
Target upside is an opinion-based scenario, not expected return or proof of value.
Missing analyst coverage alone need not reject a business; explain the limitation
and rely on stronger primary work. Material unresolved disagreement keeps it Watch.

For commodity exposure, state the actual economic driver, hedge horizon, producer
versus customer exposure and downside sensitivity. Historical equity beta cannot
replace that analysis. Optional beta needs benchmark, window, frequency and return
basis; it measures historical co-movement, not total, fundamental or binary-event risk.

Read insider filing codes and footnotes: purchases, sales, awards, exercises, tax
withholding and plans mean different things. Compare discretionary activity with
the insider's holdings, historical behavior and other insiders, not only company
market cap. A small fraction of market cap is not evidence the sale is immaterial.
Use transaction and filing dates and avoid double-counting amendments. The
[SEC investor bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-69)
explains these distinctions. No insider headline is an automatic entry/rejection.

## Event gate, statuses and ranking

Check issuer/exchange/regulator/court sources as appropriate for earnings, decisions,
hearings and other material catalysts. Record verified versus estimated dates,
timezone/time (or unknown), as-of time, holding horizon and event policy. Use the
same policy for all candidates, not the same verdict regardless of event distance.
Events weeks apart may warrant different decisions. A vendor rating is separate
analyst evidence, never a calendar gate by itself.

Define each blackout in trading sessions using an exchange calendar, with both
start and release criteria. A paper tactical policy might exclude the two sessions
before earnings through a post-release review; this is an editable assumption,
not a universal cutoff or permission. For uncertain binary events use the whole
credible date window; unknown calendar coverage cannot mean clear. Recheck before
an entry, including whether the planned holding period crosses a prohibited event.
For core research an upcoming event can block a new entry without invalidating an
existing holding or requiring a sale. Reductions/protection follow their own rules.

Keep **fundamental status** and **event status** separately:

| Display status | Meaning |
|---|---|
| Eligible | Required fundamental work supports consideration and event review is clear; still not order authorization |
| Watch | Material evidence/normalization/event review remains unresolved; state what would resolve it |
| Speculative | Material structural/cyclical/profitability risk is evidenced; cannot quietly join the core allocation |
| Reject | The stated value/growth thesis fails an evidenced required criterion; retain the failure reason |
| Event-blocked | Otherwise eligible, but an applicable event window blocks a new entry |

An event flag must not hide a Reject or Speculative fundamental status. Use the
GARCH overlay on relevant finalists after these reviews, with data audit and actual
run evidence. NORMAL is neither an eligibility requirement nor evidence of value.
GARCH may reduce sizing; it cannot rescue failed fundamentals or event clearance.

Rank comparable eligible candidates by the documented thesis, valuation range,
growth quality, downside and portfolio fit. Keep Watch/Speculative/Reject records
visible separately. A Watch ordering is research priority, not investment ranking.
Report no qualifying choice when appropriate. Portfolio sizing,
affordability, live quotes, risk_engine and applicable human authorization remain
subsequent independent steps. `screen_review.py` reports historical judgments;
never copy its status into a live `event_clear` field without a fresh event check.
