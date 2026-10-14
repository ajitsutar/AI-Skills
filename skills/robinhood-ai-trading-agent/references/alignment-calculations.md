# Explicit calculation contracts

Use the operation IDs below with `quant_workbench`; each job is
`{"id":"unique-name","operation":"operation.id","inputs":{...}}`.
[The fictional campaign](../examples/fictional-quant-campaign.json) contains runnable
jobs. Preserve the supplied inputs and run through the retained contract/report
workflow; do not replace missing fields with model-selected assumptions.

Notation: `{field,...}` names required keys, `?field` is optional, `[row]` is a JSON
array, and `name -> value` is an object map. Dates are `YYYY-MM-DD`; timestamps
include a timezone. Numeric inputs must be finite. Fractions use 0.05 for 5%,
whereas bps use 5 for five basis points. All helpers are offline research
calculations, create no orders, and impose no trading execution gates. Input
hashes establish binding to supplied content, not source authenticity.

## Planning

Every `planning.*` operation takes `inputs={"document":D}`. Every D requires
`currency` (nonblank text) and `role` (`supplied_observation`,
`hypothetical_scenario`, or `user_assumption`). Money/share fields accept finite
numbers or decimal strings. Decimal results often serialize as strings; the cash
timelines and fund expansion also use binary floats. No implicit FX conversion
occurs. `cash_plan` keeps currency balances separate. Helpers using the shared
planning validator reject currency mismatches; the portfolio-decision helpers
retain supported mismatches as unresolved context, as documented in their contract.

| Operation | Required D fields beyond currency/role |
| --- | --- |
| `planning.trade_costs` | `side`, `price`, `quantity`, `entry_orders`, `costs` |
| `planning.budget_sizing` | Explicit portfolio/alternatives mode, cash budget, selected rows and quantity scenarios; [complete contract](portfolio-decision-calculations.md) |
| `planning.friction_context` | Observed quote and explicit price/cost/slippage roles; [complete contract](portfolio-decision-calculations.md) |
| `planning.allocation_context` | Declared denominator and gross-notional rows with supplied classifications/volume/holdings; [complete contract](portfolio-decision-calculations.md) |
| `planning.input_roles` | Source/semantic roles, explicit bounds and same-basis candidate comparisons; [contract](planning-input-roles.md) |
| `planning.reference_comparison` | Requested sleeve order, explicit exposure models and supplied shocks; no inferred allocation; [contract](planning-input-roles.md) |
| `planning.dated_projection` | Dated holdings, marks, flows, earmarks, residual assets and target liabilities; [contract](portfolio-projection.md) |
| `planning.tax_sensitivity` | Explicit proceeds, costs, basis, rate and selling-cost tax treatment; [contract](portfolio-projection.md) |
| `planning.alternative_comparison` | Comparable declared criteria and alternatives; no assumed weights; [contract](planning-comparison.md) |
| `planning.settlement_transfer_paths` | Explicit listed dates/lags and date-level deadline, preserving cutoff uncertainty; [contract](planning-comparison.md) |
| `planning.cash_plan` | `as_of`, `settled_balances`, `reservations`, `floors`, `events` |
| `planning.cash_projection` | `start_at`, `end_at`, `day_count`, `annual_effective_rate`, `opening_cash`, `floor`, `events` |
| `planning.vest_reconciliation` | `as_of`, `grants` |
| `planning.portfolio_reconciliation` | `declared_equity`, `explicit_cash`, `positions`, `funds` |
| `planning.cash_reconciliation` | `mode` and the mode-specific fields below |
| `planning.trade_history_costs` | `pnl_basis`, `trades` |
| `planning.session_pnl` | `session_start`, `as_of`, `open_positions`, `closed_trades` |

`planning.trade_costs`: `side=buy|sell`, positive `price`, nonnegative `quantity`.
Each cost is `{id,unit,phase,amount}` with unique id, nonnegative amount,
`unit=per_share|per_order|bps_notional|per_round_trip`, and
`phase=entry|exit|each_side|round_trip`. A `per_round_trip` cost requires
`phase=round_trip` and `charged_at=entry|exit`; other units cannot use that phase.
Buy uses entry-phase costs; standalone sell requires
`transaction_phase=entry|exit`. `entry_orders` counts this first/standalone
transaction's orders, including for a sell; applied per-order fees require a
positive integer count. Optional `exit_price` and `exit_orders` model a long
round trip. Optional `budget` with positive `quantity_step` sizes a buy downward;
`required_net_proceeds` with `quantity_step` sizes a sale upward. Fees are charged
at explicit phases, zero quantity incurs no charge, and taxes are not inferred.

`planning.cash_plan`: the three cash maps have identical currency keys; top-level
`currency` must be one of them. Events are
`{id,kind,available_at,currency,amount,confirmed,evidence,?reservation_release}`.
**Every event needs its own currency.** IDs are unique, exact `available_at>as_of`,
`confirmed` is boolean, and accepted events require timing evidence.
`kind=cash_credit|cash_debit|withdrawal|trade_settlement|external_obligation`;
withdrawal/debit/obligation amounts must be nonpositive. Unconfirmed positive
credits are excluded. Debits precede credits at the same time. Reservation
release cannot exceed either the matching debit or remaining hold. Optional
`noncash_events` are retained separately and never fund cash demand. Separate
currency troughs/floor gaps are conditional projections, not buying power;
withdrawal dates never move to accommodate settlement.

`available_at` may also be a genuine `YYYY-MM-DD` calendar date. Declare its
`calendar_timezone` on the event or document (an event value overrides the
document value). Supported declarations are `UTC`, `Z`, a fixed `+HH:MM` or
`-HH:MM` offset, or an available IANA zone such as `America/New_York`; a fixed
offset expressly has no DST adjustment. Absent/null/`unknown` timezone remains
unknown, never the machine timezone or the offset of another event. The local
day is `[start_inclusive,end_exclusive)`, with independently localized boundaries;
ordinary DST transition days can contain 23 or 25 hours. Ambiguous or nonexistent
local midnights remain unresolved. Supply an exact availability timestamp to
resolve them. `as_of` always needs a timezone-aware timestamp. A calendar interval
entirely before opening is rejected; one overlapping opening leaves inclusion in
the opening balance unresolved, so its net effect is not asserted twice.

The date-aware result retains **every original event** in `source_events`, including
excluded unconfirmed positive credits, and records precision, declared timezone,
and interval limits in `event_timing`. No date is rewritten as observed midnight.
Its `scenarios.favorable_ordering` puts positive cash effects at their earliest
limits and nonpositive effects at their latest limits; `adverse_ordering` reverses
that ordering. End-of-day placements are symbolic limits immediately before the
exclusive boundary, never fabricated timestamps. Date-only timeline `at` fields
are null; exact event times and all withdrawal times remain supplied. Both paths
continue through **all** supplied future events after a shortfall. They expose
signed balances, remaining holds, complete cash-flow totals, and per-currency
conservation residuals; no FX conversion or inferred borrowing occurs.

`cash_bounds` gives each currency's `minimum_available_range`,
`maximum_floor_gap_range`, and `ending_available_range` plus conditional shortfall
classification. With established future calendar intervals these are ordering
bounds, and ending cash is order-independent. When timezone, date boundaries, or
opening inclusion is unresolved, `status=UNRESOLVED_TIMING` and `missing_data`
names the needed evidence. The named bounds then expressly assume every included
event is future and absent from opening cash. An unknown interval is relaxed to
anywhere after opening, even before or after every fixed event; this can be wider
than any valid local-date ordering. An opening-overlap interval is conditioned on
the event falling after `as_of`. These bounds do **not** establish final cash or
date feasibility until the missing facts are resolved. `scenario_assumptions`
and `envelope_basis` expose that distinction. No unconfirmed positive flow enters
either bound. `helper_result.timeline` and top-level `troughs` are null for the
date-aware contract because there is no single established path;
`helper_result.ending_available` is also null when timing/opening inclusion is
unresolved. All-timestamp documents retain the original exact path contract.
`spendable_cash` remains null and `execution_authorized=false` in date-aware
results; even a covered scenario is only advisory arithmetic.

`planning.cash_projection`: `day_count=ACT/365F`, `end_at>start_at`, annual
effective rate greater than -1, nonnegative opening cash/floor. Events are
`{id,at,kind,amount,confirmed}`, with unique id, timestamps within the interval,
`kind=withdrawal|deposit|cash_distribution`, and boolean confirmation. Withdrawal
amounts are nonpositive; unconfirmed positive flows are excluded. Constant-rate
compounding uses actual seconds/365 days and debits precede same-time credits.
Negative cash stops the projection with an unfunded outcome; borrowing and
deferred withdrawals are never fabricated.

`planning.vest_reconciliation`: grants are
`{id,vest_date,status,gross_shares,shares_withheld_for_tax,shares_sold_for_tax,
?assumed_vest_price,?sale}`. IDs are unique, shares nonnegative, tax shares cannot
exceed gross shares; `status=future_scheduled|vested`. A vested grant cannot have
a future vest date. Optional sale is
`{confirmed,executed_at,settled_at,sold_net_shares,net_cash_proceeds,evidence}`;
it requires an observed vested grant, `confirmed=true`, execution no later than
`as_of`, ordered dates, and quantity no greater than net shares. Only proceeds
settled by `as_of` count as observed sale cash. Grant-specific assumed values,
future stock, settled sale proceeds and spendable cash remain distinct.

`planning.portfolio_reconciliation`: positive declared equity, nonnegative
explicit cash; positions are `{symbol,asset_type,quantity,mark,?issuer_id,?sector}`
with nonnegative quantity/positive mark and `asset_type=equity|etf|cash`.
Cash assets in the inherited expansion must use `symbol=USD`. Funds map symbol
to `{as_of,evidence,holdings:[{symbol,asset_type,fraction,?issuer_id,?sector}]}`.
Fractions are in [0,1], total fund weights cannot exceed one, and cyclic funds
are rejected. Missing coverage remains unknown exposure inside identified
assets; it is separate from unexplained account equity and explicit cash.
Outputs show both declared-equity and identified-assets denominators. Optional
`contribution_allocations` maps existing symbols to nonnegative amounts and
requires `unchanged_marks_assumption=true`; contributions add equity using
existing marks, with no sales inferred. Fund timestamps are reported, not
automatically certified fresh.

`planning.cash_reconciliation`: `mode=aggregate_bridge` requires
`opening_cash,observed_cash,entries:[{id,amount}]` and compares a signed aggregate
bridge exactly. `mode=dated_ledger` requires
`opening_cash,broker_cash,as_of,entries:[{id,amount,posted_at,kind,?settles_at}]`;
posted entries cannot be future, and `kind=trade` requires `settles_at`.
The inherited dated helper uses a one-cent reconciliation tolerance and reports
unsettled positive trade proceeds. Both modes leave spendable cash unknown.

`planning.trade_history_costs`: `pnl_basis=gross_before_costs|net_after_costs`;
trades are `{id,pnl,fees,slippage}` with unique ids and nonnegative costs. Gross
and net win/loss/flat groups use their own signs; already-net P&L is not charged
twice. Costs do not establish why a trade succeeded or failed.

`planning.session_pnl`: open positions are
`{id,quantity,current_mark,?basis_per_share,?session_start_mark,
?unchanged_quantity_in_session,?session_fees}`; closed trades are
`{id,quantity,buy_price,sell_price,fees,?opened_at,?closed_at}`. Complete session
P&L requires each open position's start mark, unchanged-quantity flag true and
session fees; every closed trade must open and close within the declared
session. D also needs `coverage_complete=true` and `session_distributions`.
Missing coverage yields partial results. Optional `exchange_session_close` is
explicit; cost basis is not substituted for a prior-session mark.

## Financial scenarios

Every `financial.*` operation takes `inputs={"document":D}` and shares planning's
currency/role and decimal conventions. Money/share units must be internally
consistent; these helpers do not convert units, validate disclosures or infer
probabilities.

`financial.owner_cash_bridge`: required
`{period_start,period_end,amount_unit,reported_cfo,total_capex}`; optional
`maintenance_capex,growth_capex,sbc_added_back_in_cfo,acquisition_cash_paid,
working_capital_cfo_effect,reported_net_income`. Missing observations stay null.
Optional `cash_adjustments` rows are
`{id,amount,reported_cfo_effect,paid_on,cash_tax_treatment,evidence}`: only exact
reversals of declared CFO effects paid within the reported period enter the
supported bridge. Incomplete rows remain unresolved. Optional
`earnings_adjustments` rows are `{id,after_tax_amount,basis,rationale}`, with
`basis=explicit_assumption|supported_disclosure`; they normalize supplied net
income only and never automatically alter CFO. Capex/SBC/acquisition amounts
are nonnegative. Reported FCF, maintenance-only cash, SBC-adjusted proxy and
normalized earnings retain distinct definitions; supported adjustments do not
resolve missing bridge observations.

`financial.acquisition_cash`: required
`{pretax_synergies_per_year,tax_rate,integration_costs_by_year,
interest_cash_by_year,integration_cash_basis,interest_cash_basis,
existing_shares,new_shares,scenarios}`. Annual arrays have equal positive length;
interest entries may be null. Cash basis is
`after_tax_cash|pretax_deductible|pretax_nondeductible|unknown`. Each scenario is
`{id,ramp_fraction_by_year,delay_years,realization_fraction}`; ramp length equals
the cash arrays, ramp/realization/tax are fractions, and delay is a nonnegative
integer. Delays shift synergies only; financing/integration schedules stay fixed.
Unknown tax/interest inputs preserve unknown net cash. Existing shares are
positive, new shares nonnegative; dilution denominator is post-issue shares.
Total deal NPV needs optional `complete_deal_cashflow_contract` with
`{cashflow_basis,scope_complete,evidence_or_assumptions,annual_discount_rate,
initial_cash_outlay,dated_year_cashflows}`. Basis is `equity|enterprise`, complete
must be true, discount rate > -1, and rows are
`{years_after_initial,cash_amount,scope}` with nonnegative years and
`scope=complete_operating_cash|complete_terminal_residual`. Supply a terminal
residual row or `terminal_value_assumption=zero_explicitly`. Incremental synergy
cash alone is not total deal NPV or proof of completeness.

`financial.price_scenarios` directly prices **arbitrary dated horizons**:
`{entry_at,exit_at,day_count,entry_price,entry_cost_bps,exit_cost_bps,scenarios}`.
Use `day_count=ACT/365F`, exit after entry, positive entry price, and unique
scenarios `{id,terminal_price,cumulative_dividends_per_share}` with nonnegative
terminal price/dividends. Entry/exit bps are independently explicit in [0,10000).
Optional annual discount rate > -1 computes discounted terminal proceeds. Full
distribution PV additionally needs `dividend_timing=terminal` or each scenario's
`dividend_schedule:[{years_after_entry,amount_per_share}]`, whose nonnegative
amounts sum exactly to cumulative dividends and times fall within the horizon.
No calendar shifting, invented price target or annual operating model occurs.

`financial.terminal_scenarios` is instead a **whole-year annual operating model**:
`{starting_revenue,starting_shares,entry_price,years,amount_unit,
equity_value_floor_zero,entry_cost_bps,exit_cost_bps,reinvestment,scenarios}`.
`years` is a positive integer; revenue is nonnegative, shares positive, and the
equity-floor choice is boolean. Reinvestment is
`{maintenance_capex_fraction_revenue,
growth_capex_fraction_positive_incremental_revenue,
working_capital_fraction_incremental_revenue,working_capital_decrease_treatment}`;
fractions lie in [0,1], decrease treatment is `release|no_release|unknown`.
Each scenario is `{id,annual_revenue_growth,annual_dilution,terminal_ebit_margin,
tax_rate,exit_ev_to_ebit,net_debt_at_exit,cumulative_dividends_per_share}`;
growth >= -1, dilution > -1, margin/tax fractions, nonnegative multiple/dividends.
The distribution/PV options above also apply. Optional `sensitivities` rows are
`{id,base_scenario_id,overrides}`; overrides may contain only the seven scenario
numeric fields listed after id. Optional `scenario_probabilities` are retained,
not used to calculate a weighted value. Exit net debt is exogenous; reinvestment
is shown separately and financing is not reconciled. Interim FCF remains null.
A negative equity residual without a zero floor yields no investable price.

`financial.corporate_action_return`: required
`{start_mark_on,end_mark_on,requested_end_on,start_raw_price,end_raw_price,
new_shares_per_old,split_effective_on,dividends}`. Dates satisfy
start < end <= requested; split falls after start and by end. Starting price and
split ratio are positive; ending price nonnegative. Dividends are
`{ex_on,cash_per_share,share_basis}` with nonnegative cash and
`share_basis=old_share|new_share`. Returns use one initial old share as denominator.
Dividends outside the mark window remain visible but do not substitute for a
missing terminal mark; no reinvestment, tax or unrelated publication date is inferred.

## Strategy simulations

These operations take direct `inputs` fields, not a document wrapper. All need
`bars` and `as_of`. Each bar has
`{timestamp,session_open,session_close,open,high,low,close,volume}`. Prices are
positive finite numbers with consistent OHLC bounds; volume is nonnegative.
Timestamps are ordered, unique and timezone-aware, with last bar <= cutoff.
An optional legacy `synthetic` flag must be false/zero/empty; label fictional or
unverified material honestly with the separate `data_kind` field.

`backtest.dual_sma`: optional defaults are `fast=20,slow=60,initial_cash=1.0,
cost_per_side_bps=10,delay_bars=0,capital_fraction=1.0,terminal_policy=mark,
initial_signal_policy=enter_if_above,missed_entry_signal_indices=[],
data_kind=supplied_unverified`. Fast/slow are integers with 1 <= fast < slow;
delay is a nonnegative integer; capital fraction is (0,1], cash positive,
cost bps in [0,9999]. Daily bars end at session close, one per
nonoverlapping session. Strategy identity is `dual-sma-long-cash-1`.

Signals compare trailing completed-close means. Equality is neutral; first
complete window can enter when above, or `initial_signal_policy=cross_only`
waits for a crossover. Long/cash fractional positions fill at supplied bar open
`signal_index+1+delay_bars`. Pending fills beyond the sample are never clamped;
zero-volume due bars remain unfilled. Explicit missed-entry indices are unique
integer bar indices within the sample; they affect entries signaled there.
Costs apply to notional on both sides;
equity is marked each bar including fees. Total return divides final equity by
initial cash minus one; drawdown uses marked running peaks. Terminal policy is
`mark|liquidate_last_close`; liquidation is a predeclared boundary sale with fees,
not a same-close signal fill, and requires terminal volume. Insufficient history,
open positions and pending orders remain visible. No split adjustment, external
cash flow, market impact or actual fill evidence is inferred.

`backtest.dual_sma_variants`: requires `variants`, each
`{id,?fast,?slow,?cost_per_side_bps,?delay_bars,?capital_fraction,
?missed_entry_signal_indices}`. Shared optional inputs are
`initial_cash,terminal_policy,initial_signal_policy,data_kind` with defaults above.
First variant is baseline; all variant outcomes and parameter differences are
retained, including rejected analyses. Unknown variant keys are rejected.
Multiple changed parameters do not establish isolated causal attribution or a
selected winner.

`backtest.opening_range`: optional defaults are
`initial_cash=100000,risk_fraction=0.001,capital_fraction=0.05,slippage_bps=5,
fee_per_share=0.005,opening_bars=3,bar_minutes=5,trade_start=0,
data_kind=supplied_unverified`. Uses existing `strategy_lab` opening-range replay
with identity `strategy-lab-opening-range-breakout-1`; its result is nested under
`result` alongside explicit parameter/input/implementation hashes. The baseline
uses opening-range crossover plus relative volume, next eligible open, stop-first
OHLC ordering, 2.5R target and terminal mark. Parameters do not turn this into the
dual-SMA strategy. Intrabar sequence, queue position and live fills remain unknown.
Initial cash is positive; risk/capital fractions are in (0,1], slippage bps in
[0,9999], per-share fees nonnegative, opening bars/bar minutes positive integers,
and trade start an integer bar index within the sample. Inferred bar intervals
cannot overlap or begin before session open.

## Forward observation evidence

`validation.forward_observations` takes `inputs={"document":D}`. For admissibility,
D needs `{as_of,protocol,implementations,observations}`. Protocol is
`{start,end,frozen_at,minimum_observations}` with exact timestamps and positive
integer minimum. Implementations has `champion` and `challenger`, each
`{implementation_sha256,source_evidence,strategy_id,execution_rule,known_at}`.
Source evidence is `{source_text,sha256}`; both hashes must equal SHA256 of exact
UTF-8 supplied text. Text is never executed or imported.

Each observation needs `{id,decision_at,outcome_at,available_at,data_kind,
implementation_sha256,champion_net_return,challenger_net_return,evidence}`.
Its implementation map is `{champion:hash,challenger:hash}` matching descriptors.
Evidence is `{source_text,sha256,?pointer}`: the RFC6901-selected JSON object
(default pointer empty) must equal the row excluding `evidence`. IDs must be
unique; all occurrences of duplicates are excluded. Finite paired returns and
exact chronology must establish preregistration, decision and outcome within protocol,
outcome strictly after decision, availability no earlier than outcome and no
later than `as_of`, and implementation known by freeze and decision.
Row `data_kind=forward_paper_observation`; optional top-level `data_kind` must
not contradict it, and `fictional=true` excludes forward admission. Coarse dates
can establish contradictions but cannot supply missing exact times. Optional
`changes` is retained, never certified complete.

`validation.paper_study_forward` takes `inputs={document:D,as_of:timestamp}`.
Adapter D uses `base_strategy:{paper_start,paper_end,?entry}`, `frozen_at`,
`prespecified_criteria:{minimum_paper_observations}`, `paper_observations`,
`champion`, and `challenger` descriptors as above. Optional parent `data_kind`
and `fictional` propagate. Row `date` maps to `outcome_at` when absent;
`available_after` maps to `available_at`; missing decision time stays missing.
The returned canonical input/source mapping exposes these transformations;
row evidence must bind the canonical row. Matching entry prose never proves
matching implementations. Admission counts do not prove genuine forward
observation, actual execution, fill equivalence, change-list completeness,
forecast calibration or performance superiority.

## Typed analysis checks

Each `analysis.*` operation takes `inputs={"document":D}` and finite JSON numbers
(not decimal strings) for numerical fields.

`analysis.covariance_comparison`: D requires
`{asset_ids,base,alternative}`; unique ordered assets and same-size square
symmetric positive-semidefinite covariance matrices with nonnegative diagonals.
Optional `measurement_period` and `observation_frequency` are retained. It
reports each variance, pairwise variance ratios and a nonnegative common-scale
test with disclosed tolerances; zero denominators stay null. Stable fitted
weights alone do not identify unchanged relative risk or a causal mechanism.

`analysis.hedge_scenarios`: D requires
`{shares,price,currency,shock_returns,hedges}` with positive shares/price and shocks
>= -1. Each hedge is `{id,kind,total_explicit_cost,...}`, with unique id and
nonnegative cost. `kind=none` has no extra fields; `expiry_put` needs
`{strike,underlying_units,premium_per_unit,basis:same_underlying}`; `short_linear`
needs `{short_notional,shock_sensitivity}`. Strike/premium/notional are
nonnegative, put units positive. Put outputs are expiry payoff only; linear
sensitivity is an assumption, not estimated beta. Combined P&L fraction divides
by initial equity shares times price, excluding extra premium/collateral funding.
No pre-expiry option price, guaranteed loss bound, borrow or margin is inferred.

`analysis.compare_claim`: D requires `{left,right,relation}` with
`relation=lt|le|gt|ge|eq`. Each operand needs
`{value,unit,denominator,basis,horizon,observation_frequency,measurement_period}`
for a comparable outcome. **Denominator is a required comparability dimension.**
All six metadata fields are strings; null, absent or blank fields mean unknown.
Use explicit `not_applicable` only when justified. Mismatching fields yield
incomparability even if raw arithmetic is true. Optional `absolute_tolerance`
(default 1e-8) and `relative_tolerance` (default 1e-7) apply to equality only;
inequalities use exact boundaries. This checks declared operands and metadata,
not arbitrary prose, authentic sources or causality.
