# Shared default: Value, Quality and Momentum

Version 3.8 begins broad ranked requests with the separate
[public research campaign](research-campaign.md) and its fixed review queue.
This reference governs the strict filing-based ranking, not that vendor stage.

Use **vqm-fundamental 1.0.0** for a strict fundamental equity ranking when the user has
not selected a different saved strategy. This is the shared default for a one-year
S&P 500 request. It is a **research baseline without measured alpha or calibrated
recommendation confidence**. Equal family weights are a low-complexity convention,
not an optimized result. Never silently fall back to P/E/PEG, analyst upside or a
new model-created score because required data are inconvenient.

Read the machine-readable [profile](../profiles/vqm-fundamental-v1.json) and the
[financial normalization contract](financial-normalization.md). Keep both profile
and accounting-policy versions fixed before data retrieval. New real runs use
schema 2: the scorer derives financial fields from the shared embedded evidence.
The [fictional normalized snapshot](../examples/fictional-normalized-snapshot.json)
and [research input](../examples/fictional-normalized-screen.json) are runnable
examples with invented observations, not stock recommendations.
Start with `python scripts/research_preflight.py`. If a required component cannot
be installed through the host's supported package workflow, preserve the snapshot
and incomplete record. Qualitative research may continue with its limitations;
do not invent a substitute ranking or report a hand-calculated calendar as a
verified run. Missing optional volatility changes its status, not the factor score.

## 1. Mandate and shared information set

Resolve the requested universe, exact horizon, benchmark, fixed-hold versus review
or rebalance mandate, and requested count. If unspecified, use **all U.S.
exchange-listed stocks, including listed ADRs**. Explicit S&P 500 requests retain
that index universe and its **S&P 500 total return index** benchmark. For the broader
default, declare a U.S. total-market total-return benchmark with its source and
dividend/tax convention; ADR inclusion can differ from a domestic benchmark.
An investable ETF is a distinct comparator with fees and tracking differences.
Do not inherit an earlier chat's risk preferences when the prompt says otherwise.

For research use the last completed XNYS session, including early closes, as both
price date and information cutoff. A report released after that close enters the
next snapshot. Live execution quotes have their own freshness gates. The calendar
library is checked against retained exchange/session evidence; it is not a halt
feed. Choose providers, universe and accounting conventions before fetching.

Share the **same actual snapshot**, not just the date or this skill version.
The snapshot includes every constituent, stable issuer and security identifiers,
provider symbol mapping (e.g. a dot versus dash), dated GICS mapping and source
hashes. Reconcile fund-proxy residuals and effective membership changes. Choose
the highest ADV20 share class per issuer, breaking ties by exact symbol. ADV20
is the mean daily traded dollar volume over the last 20 complete sessions.
Missing class liquidity blocks that issuer; do not choose whichever class has
the better score. Use the issuer's total common market capitalization across
classes, even though momentum uses the selected security's return history.

Each source has a unique ID, kind, URI, provider/origin, publication time evidence,
retrieval timestamp and content SHA-256. Financial sources are regulatory filings,
then issuer releases for a later public period not yet filed. A later filing must
not rewrite an earlier as-of snapshot. Record amendments and conflicting values;
unresolved conflicts stay missing. Provider summaries alone cannot stand in for
the raw primary financial facts. Retrieval may occur after cutoff; the underlying
fact must have been publicly available by cutoff. Preserve snapshots outside the
installed skill, subject to the data provider's redistribution terms.

## 2. Fixed accounting and factor definitions

All money inputs are USD in absolute dollars, not mixed thousands/millions.
TTM is four consecutive quarters, including a 52/53-week fiscal year. `ttm_start`
and `financial_period_end` identify the interval. No forward EPS or analyst targets
enter this profile. Latest balance-sheet age is at most 185 calendar days. Check
the latest public release as well as the latest filing. Annual-only/stale data do
not become current because a vendor returned them today.

Each fact holds `value`, `unit: USD`, `source_id`, and `period_end`. Flow names
ending `_ttm` also require `period_start`. Prior balance fields carry the current
comparison's `period_end` plus `balance_date` equal to the day before `ttm_start`.
Average capital/assets means the arithmetic mean of those two balance dates.
Market cap, `close_price` and ADV20 are dated to the research close. Source IDs refer to the
embedded source register. The shared normalizer parses a conservative subset of
undimensioned Inline XBRL and accepts policy-bound reviewed table observations.
Unsupported tags/dimensions and missing components remain explicit gaps. It does
not scrape remote filings or infer absent values. Date-only publication retains
its uncertainty interval rather than inventing an SEC acceptance timestamp.
Market observations also require `observed_at` equal to that close.

When primary/event review is performed after cutoff, keep the real `checked_at`.
Add `information_as_of` equal to cutoff and `point_in_time_evidence` describing the
archived filing index/calendar used to reconstruct what was known then. Primary
publication must precede cutoff; each reconstructed event also needs its own
`published_at`. The research helper distinguishes retrieval from information time.
It does not relax live event freshness or authorize backdated broker orders.

| Adapter | Value inputs, equal weights | Quality inputs, equal weights |
|---|---|---|
| Ordinary company | EBIT / EV; (CFO − capex) / common market cap | GAAP net income / average assets; (CFO − net income) / average assets; −net debt / assets |
| Bank | Common earnings / common market cap; tangible common equity / common market cap | Common earnings / average tangible common equity; CET1 / risk-weighted assets; −nonperforming loans / gross loans |
| Insurer | Common earnings / common market cap; common equity / common market cap | Common earnings / average common equity; common equity / assets; −debt / common equity |
| Other financial | Same three formulas as insurer, in its own peer population | Same as insurer; mortgage REITs remain financial, not equity-REIT FFO peers |
| Equity REIT | Unadjusted Nareit FFO attributable to common / common market cap; (CFO − total capex) / common market cap | Common FFO / average assets; (CFO − GAAP net income) / average assets; −net debt / assets |

The executable adapter uses GICS industry 401010 for banks, 403010 for insurers,
sector 40 for other financials, and industry group 6010 for equity REITs; the
remaining ordinary operating companies use corporate metrics. A changed taxonomy
or company classification requires an explicit new mapping and full rerun.
Funds/ETFs are outside these corporate formulas. Hybrid firms need documented
mapping; unresolved business-model mismatch stays a data/evidence gap.

The normalization policy fixes parent-attributable GAAP income for `net_income_ttm`,
cash and cash equivalents only, Standardized bank capital measures, matching
retained-loan numerator/denominator scope, and disjoint debt/capex components.
Do not choose alternative tag scopes during a run; change the accounting policy
and rerun all inputs when a different convention is intended.

EBIT is reported operating income; do not add back SBC, restructuring or acquisition
costs in the score. CFO is reported operating cash flow; capex is gross cash purchases
of property/equipment and capitalized productive assets under the frozen mapping,
not net acquisitions or proceeds. Debt includes current/noncurrent borrowings and
finance leases; cash excludes restricted cash and equity investments. EV is common
market cap + debt + preferred equity + noncontrolling interest − cash. Preserve
negative earnings and FCF as signed yields. Nonpositive denominators are missing,
not extreme bargains. Preferred/NCI can be evidenced zero, never assumed zero.
REIT CFO minus total capex is **not AFFO**; maintenance/growth capex estimates and
issuer adjusted FFO are not silently substituted. Insurer/financial formulas do
not replace reserve, regulatory-capital and asset-quality diligence.

Fundamental metrics use bounded peer midranks `2*(below + 0.5*equal)/n - 1`.
Use at least eight complete unique issuers: same adapter and industry, then same
adapter and sector, then same adapter across the declared universe. Publish the
actual peer list and fallback. If still fewer than eight, leave the name unranked.
Bounded ranks already limit outlier influence; there is no extra winsorization
or model-selected clipping. All ties receive the same midrank.

Momentum is `TRI[t−21] / TRI[t−252] − 1`, using 253 consecutive completed-session
total-return-index observations through t. Splits, dividends, spinoffs and symbol
changes need an action audit tied to these exact values. This is an explicit daily
252/21 approximation to 12-minus-1 momentum, not French's exact monthly portfolio.
Rank momentum across all raw-complete unique issuers, before the peer-size gate.

Average the two Value ranks, three Quality ranks, then average V, Q and M equally.
Use Decimal arithmetic at fixed precision and symbol-ascending final tie breaks.
No imputation, favorable estimate substitution or reweighting around missing
factors is permitted. A numerical score is dimensionless, not a return, price
target, probability or proof of absolute undervaluation.

## 3. Primary review, events and completion

Review in the returned discovery order, never by the count of completed checks.
Apply the existing primary, seven-check,
event and exact-horizon review to contenders until the requested number is supported
or the available universe is exhausted. Analyst evidence is context; missing
coverage/targets are not automatic failures or invented positive evidence.
Normalization work records a reported-to-normalized bridge for the thesis but
does not overwrite the reported factors or change their weights.

Use the same decision register across models. For each check retain the source
IDs, calculation, decisive fact, status and unresolved conflict. `pass` means the
particular material question has an evidenced answer; `unresolved` means it does
not; `material_risk` identifies an evidenced speculative dependence; `fail`
identifies an evidenced contradiction to the mandate/thesis. A generic sentence
such as "quality is good" or a low multiple cannot establish a pass. Do not invent
different terminal multiples or favorable normalization to make a quota.
Shared evidence decisions are hashed in addition to numeric inputs. Disagreement
requires a separately versioned record; never overwrite a shared decision silently.

Events use the existing entry-versus-hold contract. No blanket 30-day earnings
exclusion is added. Unknown material event information remains unresolved.
Short horizons need within-window mechanisms; long horizons need rolling evidence
reviews instead of fabricated future calendars. Scenario assumptions remain
assumptions and must use the same exit and distribution/cost basis.

For the shared profile, terminal_scenarios requires
`scenario_basis: issuer_specific_valuation` and `distributions_review` with
`status: reviewed`, an `assumption` and nonempty `evidence`. Explicitly model
dividends/distributions for every issuer; zero must be an evidenced assumption,
not an omitted field or unknown dividend history. Scenario `entry_price` is the
shared `close_price`; a later executable price needs a separately labeled refresh.
The cash benchmark freshness allowance is at most seven calendar days, and the
existing helper checks its actual observation age and exact holding-period basis.
A stale three-month bill yield cannot certify a one-year excess-return column.

Uniform EPS/multiple shocks are useful **common stress tests**, not company-specific
fair values, calibrated downside estimates or substitutes for normalization.
Keep them outside the issuer terminal-valuation gate. Treat contingent guarantees,
financing facilities, customer-issued notes and recognized debt as distinct claims;
do not conflate similarly named amounts. Preserve entity, units, period and exact
filing/table reference for material claims and reconciliation differences.

Unreviewed higher-ranked contenders and any missing snapshot member prevent a
complete universe-wide claim. Show the number requested, scored, reviewed,
eligible, selected and missing, including reasons. Preserve the ordered queue to
resume. An Eligible research comparison is not a Strong Buy recommendation.
**Strong Buy is unavailable in this uncalibrated profile**, even when all records
are complete. The helper rejects that structured label; prose must follow it.

## 4. Portfolio construction and volatility

Rank first, allocate separately. Before calibration, return a comparison or a
clearly labeled paper baseline, with no score-derived expected returns. Calibrated
holding-period excess-return forecasts and covariance can enter
`scripts/benchmark_portfolio.py`, which solves:

`max (w−wb)' alpha − lambda/2 * (w−wb)' Sigma_H * (w−wb) − costs' abs(w−wprev)`.

The [fictional allocator input](../examples/fictional-benchmark-portfolio.json)
documents the schema. Forecasts/covariance must match the exact horizon,
management mode, benchmark and profile. Include the entire relevant asset set
and benchmark/current weights summing to one. Cash, if allowed, is an explicit
asset with its own return, covariance, issuer/sector exposure and constraints.
Do not treat cash alpha as zero without a justified benchmark-relative forecast.
Unselected/ineligible benchmark names may have weight zero while retaining their
benchmark exposure. Missing holdings/exposures prevent a complete allocation.

Constraints are explicit: long-only, full funding, issuer cap, active sector cap,
theme cap, half-L1 turnover cap and per-asset maximums. Set each maximum to the
stricter approved position limit and liquidity budget (participation × ADV ×
execution days / portfolio equity). Aggregate share classes by issuer and all
sleeves/account exposure through existing portfolio checks. Infeasibility produces
no allocation; never silently loosen caps. A top-ten list is not a promise that
those ten alone can meet benchmark-relative constraints.

The optimizer validates supplied declarations and numerical feasibility, not
calibration truth or optimal future performance. Apply lot/whole-share rounding,
settled-cash floors, taxes, account restrictions, fresh prices and risk checks
afterwards; rerun feasibility on the rounded proposal. It creates no orders.
GARCH/GJR/EGARCH remain validated risk ceilings only; their volatility cannot add
alpha, reverse the stock ranking or rescale a daily signal into intraday alpha.

## 5. Validation before performance claims

Follow [the validation protocol](shared-strategy-validation.md). The package ships
no historical point-in-time database, fitted alpha mapping or validated Strong Buy
threshold. Do not create one by filling fields with favorable declarations. An
implemented formula and passing software tests are not evidence of an edge.

## 6. Horizon routing and model parity

The holding clock accepts arbitrary periods without a strategy-imposed maximum.
That does not validate one alpha process across all periods. Use this profile for
fundamental research. Intraday uses registered completed-bar signals and active
session supervision; swing uses a separately versioned within-window strategy.
Do not automatically replace a one-day/day-trade prompt with VQM. For an unsupported
strategy/horizon combination, retain the real clock, identify the validation gap
and keep the analysis in research/paper mode.

For cross-model testing give each model the same prompt, mandate, snapshot and
evidence register. Require the same profile/hash, scores/order, selected names and
completion state; prose can differ. A fresh data provider pull is a distinct test.
Use bundle `compare` and then `verify` on both. The LLM extracts, explains and
flags conflicts; the executable contract computes formulas, order and selection.
Same model/version alone is not the reproducibility key. Same skill with different
data or evidence decisions can still differ; report that difference explicitly.

For a complete fictional one-year cohort, see
[the fixed-hold example](../examples/fictional-vqm-fixed-hold.json).
Bundle comparison reports shared issuer count divided by requested count. The
80% overlap threshold requires two complete lists of the requested size; empty or
short lists cannot pass it. A fictional replay establishes code conformance only,
not agreement on real stock research or investment performance.

## Research influences and implementation provenance

This repository's formulas and code are newly written conventions, not copied
implementations or a claim of replication. Research motivation:
[Asness, Moskowitz and Pedersen, Value and Momentum Everywhere](https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere),
[Asness, Frazzini and Pedersen, Quality Minus Junk](https://images.aqr.com/-/media/AQR/Documents/Insights/Working-Papers/Quality-Minus-Junk.pdf),
and [French's momentum definition](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html).
Those findings do not validate these weights, accounting adapters, universe,
implementation or current picks. No paper text, dataset or third-party strategy
code is bundled by this update.
