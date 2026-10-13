# VQM validation protocol and recommendation confidence

Status: **not empirically validated**. Freeze a validation plan before requesting
historical outcomes. Save its hash, data rights, universe/corporate-action rules,
factor profile, all variants tried, formation time, executable entry convention,
costs, benchmark and decision thresholds. Never retrofit thresholds to the result.

This protocol governs research and performance claims only. Its findings are
advisory and never conditions for native host or broker execution.

## Two experiments, two claims

1. **Fixed-hold cohorts:** form a portfolio at each predeclared monthly origin;
   enter no earlier than the first executable session after the information
   cutoff and hold for the requested year (or other exact interval). Include
   dividends, corporate actions, delistings and forced exits. Do not insert monthly
   replacements into this experiment. Record early risk exits separately where
   the mandate permits them. Compare the same dates with benchmark and cash.
2. **Monthly rebalanced portfolio:** recalculate signals at month-end and trade
   afterwards with realistic delay, spread/slippage, market impact, turnover,
   capital and constraints. This supports a monthly managed-strategy claim, not a
   claim about the unchanged set of today's ten stocks held for one year.

Use point-in-time constituents, filed/released financial vintages and actual
publication availability. Retain unsuccessful and delisted issuers, history for
past members, symbol changes, share classes and distributions. Today's constituents
with today's restated financials are not a valid historical universe. A current
snapshot from free public quotes cannot supply the missing historical database.
Disclose proxies and unavailable history, then stop short of performance claims.

## Evaluation and calibration

Separate chronological development, validation and untouched evaluation windows.
Purging removes training labels whose return intervals overlap validation/test
intervals; add a predeclared embargo appropriate to the lookback/label design.
Fit transforms or alpha calibration only using information available at each
training date. Cross-sectional ranks at formation may use that date's universe;
future labels and future membership never may.

Record net active returns, rank IC, bucket monotonicity, drawdowns, tracking error,
turnover, costs/capacity, industry and factor exposures, concentration and stability
to small parameter changes. Compare V-only, Q-only, M-only, equal VQM, equal-weight
universe and capitalization-weighted benchmark baselines under the same costs and
sample. Include all tried variants in multiple-testing assessment; hold back an
untouched period. Repeatedly consulting the test set makes it a development set.

Overlapping one-year monthly cohorts are dependent. Do not treat every cohort or
every stock-month as an independent observation or use an ordinary IID t-test.
Predeclare a dependence-aware block bootstrap/HAC method, lag/block sensitivity
and effective sample discussion. Cross-sectional observations share date and
industry shocks. Include estimation uncertainty and regime coverage rather than
annualizing a short favorable interval.

Map score/rank to horizon-specific expected **benchmark-relative total return**
with shrinkage and out-of-sample calibration. Record feature/profile hash, training
sample, exact target, currency/dividend/cost basis, management mode, horizon and
parameter-selection history. The allocator requires this separate artifact; the
dimensionless rank cannot be used as alpha. A one-year mapping cannot be stretched
to one month or a decade by multiplying time. Covariance must also represent the
actual interval; daily GARCH is not automatically Sigma for a year.

## Recommendation labels and performance evidence

There is no enabled Strong Buy classifier in v3.7. Software will not generate that
label. A future version needs a predeclared, empirically supported net excess-return
threshold with uncertainty bounds, enough independent evaluation evidence, failure
and drawdown limits, stable regime behavior, and separate current-company evidence.
Being top-N or above the cross-sectional median is insufficient. Keep an explicit
abstention option and validate label calibration on untouched observations.

Strategy cards and forward observations help assess whether backtest assumptions
survive new data; they are not prerequisites for a user-requested transaction.
Daily/swing/intraday strategies each need an applicable test design and cost model
to support performance claims. Arbitrary horizon parsing does not expand a model's
validated operating range. Execution belongs to native host and broker tools;
`execution_handoff.py` only preserves the supplied request.

## Reproducibility acceptance

For actual independent-model trials, the acceptance target is **at least 80% of
the requested names in common**: eight shared unique issuers in two ten-stock
lists. This is intersection count divided by requested N, not Jaccard similarity.
Keep universe, information cutoff, profile, prompt and test data/entitlements
comparable; record differences and distinguish issuer overlap from exact order.
`research_bundle compare` emits this diagnostic for full selected lists. Fewer
than N in either list is INSUFFICIENT_FULL_LISTS, not a passing overlap test.
Do not pad lists, weaken evidence or count two empty lists as agreement. Compare
research priorities separately from Eligible selections and Strong Buy claims.

Identical frozen input and decision-register replays still require **100% exact
order agreement**. An 80% external-model acceptance floor does not authorize
randomness or overrides in the engine. Record actual provider/model/settings,
prompt, attachments and returned artifacts for a real model test. A second Codex
response labeled "Claude" is a simulation, never a Claude observation. Fictional
conformance cases test workflow mechanics, not stock-pick overlap in fresh real
S&P 500 research or investment performance.

Software tests use fictional snapshots to check formulas, negative earnings,
point-in-time cutoffs, adapters, missingness, ties, issuer deduplication and replay.
They do not count as investment validation. Independent model runs must use the
same raw snapshot and decision register; compare exact discovery/selection and
status outputs. Changed prose is acceptable; changed economics, sources or
eligibility is a separately identified input disagreement.

Research context for avoiding combinatorial overfitting:
[Novy-Marx, Backtesting Strategies Based on Multiple Signals](https://www.nber.org/papers/w21329).
This protocol does not bundle that paper's code or claim its results for this skill.

## Recorded cross-model execution

See [the October 10 validation record](cross-model-validation-2026-10-10.md) for
actual v3.7 conformance and a separate Yahoo-data approximation that achieved
100% top-ten overlap. The latter does not relax strict filing eligibility or
guarantee agreement when models acquire and interpret fresh data independently.
