# Quant workbench input and replay contract

New helpers are offline except the explicit SEC fetch subcommand. Use the pinned
requirements-tested.txt environment for comparison. They return calculations and
proposals, never orders. `examples/fictional-quant-campaign.json` exercises the
interfaces below; it is synthetic test data, not an investment result.

```text
python scripts/research_preflight.py
python scripts/quant_workbench.py operations
python scripts/quant_workbench.py prepare examples/fictional-quant-campaign.json --output ../runtime/quant.inputs.json
python scripts/quant_workbench.py run ../runtime/quant.inputs.json --output ../runtime/quant.bundle.json
python scripts/quant_workbench.py verify ../runtime/quant.bundle.json
python scripts/quant_workbench.py compare ../runtime/codex.bundle.json ../runtime/muse.bundle.json
```

Choose a runtime directory outside the installed skill, create that parent, and
use a new output filename. Never overwrite a frozen bundle or substitute synthetic
input for a real market request.

## Envelope and operations

Input: `{schema_version:1, contract:{prompt,purpose,base_currency,horizon_id,as_of}, jobs:[...]}`.
Each job has a unique `id`, an allowlisted `operation` and named-argument `inputs`.
Dates require timezones. New numeric helpers take JSON numbers, decimal returns,
rates/weights/shocks and explicit currencies/frequencies. Existing financial
normalization retains its separate Decimal-string schema. Missing values are not
zero. Inputs cannot supply code, imports, shell commands or executable callbacks.

| Operation | Arguments |
|---|---|
| `validation.folds` | `samples:[{id,start,label_end,feature_available_at}],min_train,test_size,gap_seconds` |
| `validation.tail` | `returns,confidence` (defaults 0.975); empirical loss VaR/ES and drawdown |
| `validation.hac` | `returns,lags`; prespecified serial-correlation lag count |
| `validation.holm` | Complete `p_values:{trial:p},alpha`; familywise adjustment |
| `validation.sharpe` | Net excess `returns,trial_sharpes,effective_trials,iid_assumption_justified`; same unannualized frequency |
| `validation.bootstrap` | `returns,block_length,replications,seed`; seeded circular block interval |
| `validation.factors` | `observations:[{timestamp,excess_return,factors:{name:value}}],factor_names,lags` |
| `validation.promotion` | `evidence,criteria`; complete aligned net-excess trial returns and frozen/test chronology |
| `portfolio.construct` | `document` with allocation contract below |
| `risk.option` | `spot,strike,years,volatility,rate,dividend_yield,right,exercise_style`; European only |
| `risk.bond` | `cashflows:[{years,amount}],zero_rates,spread,callable`; fixed noncallable flows, continuous rates |
| `risk.scenarios` | `positions,scenarios,nav,base_currency`; explicit multipliers, FX and shocks for every position |
| `ops.cash_ladder` | `as_of,settled_balances,reservations,events,floors`; per currency, only confirmed credits |
| `ops.shortfall` | `side,intended_quantity,decision_price,arrival_price,terminal_price,fills,fees` |
| `ops.xirr` | `cashflows:[{at,amount}]`; investor contributions negative, distributions/terminal NAV positive |
| `ops.attribution` | `groups` with beginning portfolio/benchmark weights and returns, including cash |
| `data.sec_extract` | `payload,cik,information_cutoff,concepts:[{name,namespace,tag,unit}]` |
| `data.coverage` | Existing strict `normalization_input`; recomputes actual missing-field tasks |
| `backtest.portfolio` | `document` with aligned returns, causal decisions, costs, capacity and benchmark |
| `monitor.assess` | `as_of,observations_at,returns,periods_per_year,forecast_volatility,coverage,execution_cost_bps,reconciliation_difference,limits` |

Some arguments have documented defaults in their Python signature. To compare
models, run `operations` to inspect the actual allowlisted signatures and `prepare`
to materialize those defaults in a new input document before computing. Preparation
preserves explicit arguments, does not fill missing observations, and does not
choose portfolio constraints, forecasts or nested strategy settings for the user.
It reports missing required or unknown arguments instead of inventing them.
Each computed job records its resolved-input hash and any defaults applied at run
time. Compare these with the retained raw input, rather than reconstructing an
operation from a prose answer. Prepared inputs with the same contract produce the
same calculation request irrespective of the model that launches them.

Bundles record Python, platform and relevant installed dependency versions. Use
the pinned requirements for a controlled comparison and report remaining platform
differences. A failed optimizer, unsupported operation or missing dependency is an
observed outcome; do not replace it with a claimed successful model computation.
Code replay proves that calculation's reproducibility, not investment effectiveness.

Use retained named helper facts for numeric conclusions they support, preserving
their units, denominator and horizon. Identify additional calculations and
inference separately and retain supporting calculation code or helper results.
For an optional JSON/Markdown table of retained results, use
[report facts](report-facts.md). The adapter names supported metrics and retains
source pointers, including rejected/nested statuses; it does not replay the job
or establish the validity of selected inputs or a surrounding narrative.

When optional `quant_controls` are chosen for an analytical evaluation, the report's
`quant_evidence` must also declare matching `strategy_setup` and `strategy_version`.
Its trial IDs must exactly match the report's `variants_tried` string list, and
its market `input_data_hashes` must be retained in the report's `input_hashes`
name-to-SHA-256 map. Test windows must match. This prevents unrelated quantitative
evidence from being attributed to a different strategy version; it does not authenticate the
underlying registry or source files by itself.

## Allocation

Document fields: `assets,covariance_ids,covariance,currency,horizon_id,covariance_horizon_id,risk_estimated_at,decision_at,objective,constraints,scenarios`.
Covariance, returns and costs refer to the actual same holding period; no implicit
annualization. The asset order must match covariance and every scenario vector.

Each asset: `id,issuer,groups,currency,instrument_model,eligible,previous_weight,min_weight,max_weight,one_way_cost,impact_coefficient,borrow_cost_per_period,max_trade_weight`.
Instrument model must be `cash_funded_linear`. Bounds allow exit; ineligible names
are forced to zero. A negative bound needs `borrow_available` and `borrow_evidence`.
Capacity is a fraction of NAV derived from actual volume/participation and time.

Constraints: `net_target,gross_cap,gross_turnover_cap,cash_floor,collateral_reserve,risk_aversion,issuer_gross_cap,group_gross_caps`.
Gross turnover is sum of absolute risky-weight changes, not half-turnover. Optional
`volatility_cap` and `tracking_volatility_cap` use the covariance horizon; tracking
also needs asset `benchmark_weight`. Scenarios: `{name,returns,max_loss_fraction}`.
Costs reduce scenario P&L/free cash. Declared collateral is not a broker margin model.

`minimum_risk` needs no forecast. `robust_return` additionally needs asset
`expected_return,return_uncertainty` and calibration with matching horizon/currency,
holding-period total-return units, frozen/test dates, retained evidence and all
trials. Calibration is a declaration to verify, not engine-proven alpha. The solver
audits actual weights and returns infeasibility rather than relaxing constraints.
Continuous weights still need lot, settlement, tax and broker feasibility checks.

Cash events may declare `reservation_release` only against a matching debit,
up to that debit and the remaining opening reservation in the same currency.
This consumes an existing hold without charging it twice. Retain order-to-hold
evidence; aggregate currency checks do not prove the reservation belongs to that
order. Omitted releases conservatively keep the hold. Do not count cancelled
orders as spendable until the broker confirms cash is available.

## Backtest, monitoring and primary data

The period simulator requires beginning decisions known before the return interval,
aligned total returns, cash/benchmark returns, tradability, one-way costs, impact,
trade-value capacity and universe/corporate-action evidence. It charges costs before
returns and does not model settlement-funded reinvestment or intraday queue fills.
Its `validated_for_live` remains false. Use strategy_lab for its supported event
simulations and paper-test actual order mechanics separately.

Monitor thresholds are fixed before observing the result. Match the realized-return
window/frequency to forecast volatility. A clear supplementary monitor cannot
authorize an order; a breach cannot silently retune models or raise limits.

SEC acquisition: `python scripts/primary_financial_data.py fetch --cik VERIFIED_CIK --user-agent "CONFIGURED_IDENTITY_AND_CONTACT" --output NEW_DOWNLOAD_DIRECTORY`.
Supply the user's configured SEC contact identity and a verified CIK. Create only
the output parent. Denial/rate limit stops the request; do not rotate identities.
Extract with `python scripts/primary_financial_data.py extract INPUT_JSON`.
Retain original filings for context/accuracy/custom metric review before using
financial_normalize; API values alone cannot clear filing eligibility.

## Cross-model acceptance

Verify both original bundles and their hashes before comparison. Numeric tolerance
is absolute 1e-8 and relative 1e-7; strings, statuses, job order, keys and rejection
decisions must match exactly. Different inputs fail the calculation test. Record
environment differences; pins and code hashes are part of reproducibility.
Linear-algebra failures are recorded per job as `CALCULATION_FAILED` with no
numerical result or fallback; other independent jobs may finish. Invalid inputs
remain `REJECTED_INPUT`. Neither status may be counted as a successful calculation.
Compare the model's routing/explanation separately against a prespecified rubric.
An expected input rejection demonstrates a guard, not a successful investment.
Cross-model consistency, independent source acquisition and strategy performance
are three different validation claims.

The legacy `validation.promotion` operation name describes an evidence assessment,
not live activation. All workbench findings are advisory and impose no execution
gates, price-drift thresholds or additional approvals.
