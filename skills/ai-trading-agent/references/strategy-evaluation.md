# VQM evaluation methods and recommendation confidence

Status: **not empirically validated**. Freeze a validation plan before requesting
historical outcomes. Save its hash, data rights, universe/corporate-action rules,
factor profile, all variants tried, formation time, executable entry convention,
costs, benchmark and decision thresholds. Never retrofit thresholds to the result.

This protocol governs research and performance claims only. Its findings are
advisory and never conditions for native host or broker execution.

## Prospective strategy design

When the original request contains one literal local JSON reference, begin at `research_preflight.py --request PROMPT.txt --source-root INPUTS --source DOCUMENT.json`. It reads the selected record before the assistant chooses methods. File names are relative to INPUTS; use an explicit allowlist and retain the original prompt bytes. For example, a reference of `studies.json#/cohorts/0` selects the first cohort. Bare references run to whitespace and keep punctuation inside the key. Use backticks or angle brackets for paths or keys with spaces, surrounding markup or ambiguous sentence punctuation. A missing or ambiguous selector needs clarification. This operation does not infer intent from keywords. For a new single-instrument long/cash design, add the [typed registration and executable economics](strategy-registration.md#executable-return-and-execution-conventions) to the four choice fields (`design_kind`, `design_terms`, `proposed_decision_rules`, `answer_controls`) and repeat with `--scoped-design CHOICES.json --private-output OUTPUT`. This dispatches to the renderer and replays the original selector and source hashes during verification. Proposals still require substantive review. The scoped readback binds decision, holding period and horizon to fields in the selected record. Optionally map those roles to nested record-relative pointers in `CHOICES.clock_fields`. Omit missing roles. An enclosing or sibling field does not establish a second user mandate. A separately requested horizon needs its own source. Generic `route-horizon` evaluates caller declarations and cannot establish that the user selected one of those siblings.

In this mode the delivered response generates its strategy `limitations` from the selected report. Omit that field in the host metadata. Keep genuine runtime and collection disclosures in `execution_limitations` or the host's designated runtime field. Preserve other case-specific evidence gaps in the strategy design itself. The earlier `--executable-design` interface remains available for existing callers and replay.

For a final research design or forward-paper answer with an already bound structured selection, run `scripts/research_contracts.py strategy-answer REQUEST.json --source-root INPUTS --private-output OUTPUT`. Keep the original source bytes intact and select the record named by the request. Use the exact source ID, digest and record pointer. Treat fields in its parent and siblings as outside scope. Separate observations and assumptions from proposals. A source binding verifies the selected bytes. A reviewer still needs to judge the meaning of a proposal and whether it conflicts with a supplied rule.

For new research and paper protocols use the [typed strategy registration](strategy-registration.md). It gives each comparator input an explicit origin, commits to one uncertainty estimator, and separates historical development from the evaluation window. Free-text designs accepted by the legacy interface have an open-prose registration scope.

Start with the request fields below and the `strategy_answer` controls shown by `research_contracts.py schema`. For this operation omit the legacy `design_terms.variant_treatment`. Specify one structured variant policy:

- `fixed_primary` takes `primary` as either a selected-record-relative `record_pointer` or a labeled `proposal`. Only that primary can pass; report alternatives as descriptive sensitivities.
- `development_selection` also requires a predeclared `selection_measure`, `tie_break`, `multiplicity_adjustment` and `lock_before`. State precisely how the winner is chosen and which untouched observations may decide the outcome.

Declare the initial position and regime, eligible-session/time-zone convention, and actual warm-up history. Derive a first actionable timestamp only from verified observations and an eligible calendar. Set a justified number of paired observations and completed events, with their units. Link a one-sided confidence bound to a zero-based directional performance-rule index. Specify the estimator, confidence level, dependence treatment and its parameters. Gates and thresholds are design proposals until frozen before observations. Sparse data or an unavailable bound is inconclusive. The forward-paper answer includes the proposed journal fields for decision, quote, order, execution and balance reconciliation.

For a structured response, put the destination's required host declarations in a JSON object (`HOST.json`). Include applicable runtime details, limitations and evidence references. The helper supplies `rows` and `first_response_sha256`. Use `{}` if no host fields are required. Generate the final files from the selected strategy:

```text
python scripts/research_contracts.py deliver-strategy OUTPUT --metadata HOST.json --private-output NEW
```

Choose a fresh private directory name under an existing local parent. On success submit the exact `NEW/files/first-response.md` and `NEW/files/response.json`. The command verifies the pair against the replay, checks the preserved metadata values and prints local file hashes. If the destination requires another location, copy both files unchanged and run `research_contracts.py verify OUTPUT --answer FINAL.md --rows FINAL.json --metadata HOST.json` on the actual copies. For a text-only response use `OUTPUT/answer.md` unchanged and verify the destination with `--answer FINAL.md`. To change strategy content, correct the request and generate a new export. Plain `verify OUTPUT` checks the retained export only. The checks establish local consistency. Host declarations, strategy quality and receipt by the recipient require separate evidence.

### Checking a forward-paper execution journal

Each new forward-paper answer includes a typed reconciliation policy for expected decision slots, intended orders and independent executions. Apply the policy before evaluating execution-quality tolerances. For example, a documented failure to fill is a measurable outcome. An intended order missing from the disposition journal leaves its outcome unknown.

For an observed variant and window, run `python scripts/forward_reconciliation.py REGISTERS.json`. Give `decisions`, `orders` and `fills` a `reference` and `accounted` list. Use unique decision IDs, then `[decision_id, intended_order_id]` and `[intended_order_id, execution_id]` pairs. Use `null` for an unknown parent or unavailable list, and `[]` for a verified empty list. Build each reference population independently of the journal being checked. Count each intended order once across partial fills. Keep separate records for the primary strategy and each sensitivity.

Supply `unresolved_exceptions` as a list of open exception IDs after checking quantities, prices, quotes, fees, cash and positions against separate originals. Use `null` while that check is unavailable. The helper compares identity sets and reports distinct matched fill parents. Inspect the actual numbers, criteria and study-specific sample requirement separately.

When asked to write a contract, make the design choices the request delegates. If
the input selects a record, anchor supplied facts to that exact file and pointer.
An account goal, example trade, fee schedule or risk budget elsewhere in a document
needs an explicit relationship before it can change the selected strategy. Keep
the signal clock, holding period and evaluation dates separate. State how ties,
warm-up, order timing, costs, missing observations and exits are handled. Preserve
supplied variants and identify the primary rule and how alternatives affect the
decision. State the basis for any new choice and retain genuine conflicts for review.

Use `scripts/research_contracts.py plan-strategy REQUEST.json --source-root INPUTS
--private-output OUTPUT` to record the design. Use the existing source allowlist and
SHA-256 contract from `schema`. Set `strategy_source` to the source ID and JSON
pointer of the requested record. In `design_terms`, use `{"record_pointer":"/field"}`
to reuse a value within it or `{"proposal":"specific proposed convention"}` to
add a choice. Supply benchmark, variant_treatment, evaluation_window and
execution_convention. Name the comparator and match dates, currency, reinvestment
and cost basis. Keep the complete original strategy in view alongside these terms.

For `design_kind=research_contract`, supply development_validation_split. Designate
chronological development and validation folds and a final evaluation window,
including leakage controls. Specify the variant-selection or multiplicity policy.
Date the proposal. If part of a planned evaluation interval has already elapsed,
state what evidence would establish independence and how an exposed interval will
be treated. Missing observations limit empirical claims while a proposal remains feasible.

For `design_kind=forward_paper`, supply variant_decision_record and
quote_order_fill_reconciliation. Record each variant's inputs, decision time and
action, including no-signal decisions. Link timestamped bid/ask, size and freshness,
order arrival/acknowledgement, partial or missed fills, fees, latency, and the final
cash and position reconciliation. Specify the reference price and quantity for
shortfall and separate modeled costs from observed costs. State what independently
retained evidence and review would support consideration of live use.

For each proposed decision rule supply purpose, measure, units, measurement_window,
comparison, numeric threshold, on_failure and if_unmeasurable. For example a design
may **propose** that mean paired net active return, in percentage points per
observation over the designated holdout, must exceed zero, with a confidence bound
and drawdown tolerance appropriate to the strategy. Justify the chosen values
and precommit uncertainty and sample-adequacy treatment. A research contract
needs performance and risk rules. A forward protocol needs performance, risk and
operational rules, such as a specified maximum proportion of unlinked fills.
Report missing design fields and data separately. This operation checks the
structure of an authored proposal. It does not grade a strategy or establish
that the rules were precommitted or that a paper trade occurred.

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

There is no enabled Strong Buy classifier. Software will not generate that
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
