# Portfolio-manager operating contract

Read for multi-asset allocation, quant strategy development, hedging, or requests to
operate as an investment manager. Use [quant-research.md](quant-research.md) for
method selection and [quant-workbench.md](quant-workbench.md) for executable inputs.
The scope is research, recommendations and advisory operational analysis. Do not describe a chat
session as a fiduciary, custodian, audited fund administrator or always-on OMS.

## Start with the mandate

Record base currency, objectives, benchmark, capital, liabilities/redemptions,
tax/account jurisdiction, permitted instruments, leverage/short permissions,
holding/exit contract, drawdown and liquidity budgets, concentration/factor limits,
the requested transaction context when relevant. Keep requested research separate from
authorization to trade. When the user requests a screen without personal
preferences, apply its documented research contract; do not invent an investment
policy or demand a personal questionnaire before useful research.

Resolve decisions at three levels: total portfolio and liabilities; capital/risk
allocation among strategies; individual security/position sizing. Multiple tickers
or managers can represent the same issuer, factor, currency or collateral risk.
Compare no action, cash/T-bills, a diversified passive baseline, and the proposed
active portfolio after implementation costs. Maximum expected gain without a loss,
liquidity and leverage constraint is an incomplete optimization objective.

## Deterministic research and model governance

Keep the existing named public VQM discovery profile unchanged unless the user
selects another versioned strategy. More analytics must not silently change its
weights, accounting definitions or picks. A research request for another horizon
uses the actual horizon contract; daily VQM is not a day-trading entry signal.

Freeze input universe, legal-entity identifiers, information cutoff, data vintages,
price adjustments, return frequency, currency, benchmark, costs, feature/label
definitions, peer membership, parameters, seed, code and dependency versions.
Separate discovery data from primary financial verification and real-time execution
quotes. Store every tested variant in a trial registry, including failures.

The model's role is to acquire/review evidence, choose the authorized saved workflow,
and explain outputs. Numeric operations run through retained code. Model narration
cannot modify a computed ranking, waive a failed constraint, change a time horizon,
or turn research results into execution permission. Record discretionary judgments and their affected names
separately. A second model must receive the same complete package and contract,
not another model's picks. Compare data completeness and rejection decisions as
well as numbers. Same-input replay tests and independent-data agreement are
different experiments. Neither establishes investment performance.

For a model change, preserve the champion, test a challenger on frozen data and
new paper observations, review material deviations, and roll back on a failure.
Do not tune to achieve cross-model overlap or to repair a losing test. Use an
independent evidence review when practical; independent reviewers do not gain
authority to place trades or alter the mandate.

## Financial-data recovery

All members of a requested universe must have an explicit attempted/scored/reviewed
status. Recover missing provider components before comparing results. For remaining
financial gaps, run the primary-data extraction and normalization backlog; use
issuer filings and supplements, not favorable imputation or a different accounting
basis. Bank/REIT adapters already exist in the strict normalizer: missing data in
the vendor queue does not mean the investment is prohibited or inferior.

`primary_financial_data.py` fetches SEC companyfacts with a configured contact user
agent, preserves bytes and receipts, and extracts only date-admissible candidates.
Original filing contexts, accuracy and supplemental/custom tags still need review.
`data.coverage` recomputes the existing normalizer and returns each actual missing
field with its source route. Complete a shared reviewed record and rerun normalization.

For banks, use listed holding-company scope, standardized CET1/RWA, exact tangible
common equity and matched loan/nonaccrual definitions. Do not substitute subsidiary
Call Reports. For equity REITs, reconcile common unadjusted Nareit FFO with GAAP;
AFFO, adjusted FFO and diluted FFO are distinct. For insurers, supplement the
common-equity adapter with underwriting, reserving, reinsurance and capital review.
For negative earnings/cyclicals, retain signed yields and cycle risks; never turn
negative P/E into cheapness. Sector-specific supplementary metrics are review
evidence until a new score profile is explicitly defined and validated.

Do not mix vendor-derived and primary-derived factors in a supposedly uniform
strict ranking. Preserve the vendor candidate queue and publish a separately
versioned strict ranking when common primary evidence is complete. If recoveries
remain unresolved, state the coverage limitation instead of calling a subset the
entire index's best investments. No arbitrary candidate count fills evidence gaps.

## Construction, validation and trading

Use `quant_portfolio.py` for a risk-first allocation with explicit cash, collateral,
gross/net, issuer/group, turnover, liquidity, volatility and scenario constraints.
Its optional return objective requires a separately documented out-of-sample return
calibration. A dimensionless factor score, analyst target or narrative conviction
is not expected return. Inspect estimation sensitivity, constraint binding,
concentration and an uncomplicated baseline before accepting an optimized proposal.
Continuous weights are not affordable shares or executable orders.

### Calibration audit boundaries

Audit the declared profile, horizon, return units, benchmark and management mode,
then distinguish contract consistency from verified forecast provenance and
empirical adequacy. A successful solver or a nonempty evidence field establishes
neither calibrated expected returns nor suitable investment weights.

Check the selected operation's actual field semantics, defaults and metadata
scope before declaring a required input missing. Apply document or calibration
units and horizon to asset values when that operation defines them there; do not
require duplicate per-asset fields or rename a valid input to match another
workflow. For example, `benchmark_portfolio.py` consumes asset `alpha` under its
document/calibration excess-return contract; the separate `quant_portfolio.py`
robust-return contract does not add `expected_return` or `return_uncertainty`
requirements to it. Missing empirical mapping or uncertainty evidence is a
validation limitation, not proof that a particular literal key is required.
A label's presence or absence alone neither proves nor disproves provenance.
A scan finding no factor-score or analyst-upside keys supports only that limited
observation, not a claim that supplied returns were never derived from them.
Distinguish no substitution performed during this audit from unverified upstream
derivation; establish provenance from retained source and transformation evidence.

Report training, freeze, test and as-of ordering with retained operands. A gap
between periods is an observed interval, not an automatic defect or a requirement
to add observations. A deliberate embargo or untouched holdout may explain it,
but do not assert that explanation without evidence. Apply an explicit coverage
requirement when one is supplied; otherwise disclose the gap and its unknown
purpose without inventing continuous-calendar coverage as a prerequisite.

Report evidence age separately from freshness compliance. Classify an age limit
as met or unmet only against an applicable declared recency rule; an observed
regime or data change can separately support a relevance concern. Without either,
state that recency adequacy is unassessed, not that elapsed time alone proves
staleness. Newer evaluation may be recommended as additional research, but must
not be presented as a mandatory missing interval absent that requirement.
Keep timestamp precision and time zones: report exact elapsed durations or label
whole-day truncation/calendar-date differences explicitly. Do not describe a
truncated duration as an exact timestamp difference.

Carry the same scope and conditions into the final recommendation and any
`missing_requirements` list. Separate missing empirical evidence for a claimed
calibration from missing policy needed only to assess compliance with that policy.
An absent recency or coverage policy remains unassessed; it is not by itself a
prerequisite to empirical calibration unless the selected contract or user requires
it. Attach each applicable condition to its own checklist item, rather than relying
on an earlier qualification or a trailing condition for a different item. Keep
optional research recommendations separate from requirements. A correct overall
verdict does not justify adding unsupported prerequisites in its remedy.

Inventory the evidence field and every retained supporting ledger separately.
A disclaimer or schema-only label does not erase supplied numerical observations;
those observations also do not validate a fitted model, trial completeness,
asset-return mapping or forecast provenance by their mere presence. Compute and
qualify supported descriptive metrics for every supplied variant; retain unknown
all-trial completeness, shared-outcome dependence and missing validation details.
State which conclusion follows from which evidence rather than converting a
field-level absence into a claim that the entire calibration record is absent.
Variants evaluated on the same outcomes form a paired comparison. Shared outcomes
do not by themselves invalidate it or require disjoint datasets or independent
replications. Do not count duplicated outcomes as additional independent sample
size; assess dependence, selection and the evaluation design for the particular
inference being claimed. Aggregate error rankings do not establish that every
individual error is smaller. Check aligned observations before making elementwise
claims; distinguish aggregate metrics, maximum errors and pointwise comparisons,
and retain tradeoffs when variants rank differently across metrics.

For strategy development use causal data, purged expanding-window splits, a final
untouched test, net costs, a complete variant registry, serial-dependence-aware
inference, and forward paper execution. The period portfolio simulator and the
intraday event simulator have different scope; neither validates queue fills or
entitlements. Optional `quant_controls` recompute research tests from retained
trial returns. Their results describe evidence quality and do not create an
execution prerequisite or a strategy-promotion requirement.

Use [multi-asset-playbook.md](multi-asset-playbook.md) for the instrument/strategy
route. Identify missing analytical models and preserve the instrument's actual
type. Native host and broker tools determine available transactions and enforce
their own permissions. The skill has no execution gates; `execution_handoff.py`
preserves a requested payload without submitting it or issuing approval.

## Daily operation and incidents

For portfolio analysis, compare cash, positions, corporate actions, open orders and
manual activity; refresh quotes/events; check settled cash and currency-specific
liabilities/collateral; run exposure, tail loss, full scenario and liquidity checks.
Use `ops.cash_ladder` to expose funding gaps without spending unconfirmed sales.
Broker availability, not a calendar estimate, controls a real purchase.

During the session: check fills, partial protection, stale feeds, spreads/halts,
borrow recalls, margin/settlement restrictions, model drift and risk consumption.
`monitor.assess` reports advisory alerts for stale data, coverage, volatility,
cost or reconciliation differences. It never blocks an order, cancels protection,
retunes a strategy or changes a broker setting.

On disconnect/unknown submission: preserve the journal, reconcile broker state and
handoff residual exposure. No blind retries. On close: match broker fills/cash/lots,
record valuation uncertainty, residual positions and upcoming obligations. Measure
TWR, investor money-weighted return, costs, drawdown and benchmark/factor attribution
separately. Preserve incident history and distinguish observed resolution from
an assumption; historical records are not local execution locks.

## What must remain external

Custody, exchange/broker entitlements, legal/compliance decisions, audited NAV,
tax returns, subscriptions/redemptions, valuation of illiquid/exotic assets, and
resilient 24/7 execution infrastructure are not supplied by a skill. A successful
unit test, paper simulation or model-agreement test cannot replace them. Do useful
analysis within available scope and identify the concrete missing dependency.
