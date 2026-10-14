# Preserve planning input roles and comparison scope

Use `planning.input_roles` and `planning.reference_comparison` through the normal
source-bound workflow. These are advisory interpretation helpers. They do not
establish source truth, broker availability, execution permission or suitability.
Their input roles are explicit declarations to check against the full request.

For a retained planning source with `capital`, `contribution`, or a `trade` block,
use `planning.source_roles` first. Its document contains `currency`, `role`, the
whole `source` object, `source_ref` (file plus `#` prefix), `source_role`, and optional
`checks`. It binds the original fields to the role operation without an invented
holdings ledger. `trade.maximum_planned_loss` has metric `planned_loss`; its basis
is null unless `trade.maximum_planned_loss_basis` is explicitly supplied. Entry,
exit, slippage, fees or a stop do not resolve that basis. Preserve the null in the
answer and any comparison; named gross/after-cost sensitivities are separate.

## Assign a role before calculating

Keep these separate even when two supplied numbers happen to match:

| Meaning | Interpretation |
|---|---|
| Observation | An explicitly supplied account or scenario observation with its own source role |
| Maximum | Candidate quantity or metric must be less than or equal to the ceiling; no equality target |
| Minimum | Candidate metric must be greater than or equal to the floor |
| Target | A declared desired amount; distinguish it from an observed state or maximum |
| Pending | Preserve the stated amount and state; unknown state is not an order hold, position or proposed new trade |
| Scenario | Conditional input, including any constructed empty ledger or cash-only alternative |
| Unknown | Unresolved meaning, including missing state or provenance |

An absent holdings ledger does not mean an empty ledger. An explicit empty ledger
in a hypothetical scenario still does not establish actual holdings. Cash in an
illustrative trade block need not equal settled account cash. Never invent
`positions=[]` to turn partial inputs into an observed account reconciliation.
An explicit source observation with an empty ledger remains distinguishable from
both missing data and a constructed empty scenario; its authenticity is unchecked.

A pending amount alone does not identify the requested trade or its quantity.
Even an explicit reservation needs separate timing and inclusion evidence before
deducting it from a cash amount: avoid subtracting a commitment already included
in the supplied balance. Preserve unknown state and show any conditional accounting
interpretations separately. Do not choose one as the primary cash plan.

Compare a candidate loss to a maximum as an inequality. A smaller candidate loss
can satisfy a ceiling; different dollar exposure and loss limits are not conflicting
sizing equalities. Keep gross loss, after-cost loss, exposure, cash debit and guaranteed
worst-case loss distinct. Use `planning.trade_costs` for explicit price/quantity/cost
scenarios, then pass its after-cost loss as a candidate against a compatible limit.
A stop-price scenario does not establish a maximum realized loss. A ceiling alone
does not request a maximum-size trade; calculate one only when the user requests it,
with all necessary costs, quantity increments and constraints declared separately.

## Shared comparison convention when weights are not supplied

For a request comparing portfolio sleeves, preserve the requested sleeve order and
first present the same source-backed comparison scope for each: allocation evidence,
holdings evidence, strategy/return evidence and missing inputs. Leave missing
allocations unknown. Discuss horizon, liquidity, concentration and trading costs
using the supplied objectives and rules. A daily strategy does not become an intraday
strategy, and a sleeve name does not define securities, turnover or a risk model.

Use the named `declared-capabilities-and-unit-price-exposure-1` convention if a
normalized price sensitivity helps. This uses **one currency unit of exposed
notional** as an analytical denominator for explicitly declared `long_linear_price`
references. Its relation is `price P&L / exposed notional = supplied price return`.
It is not an actual allocation, position, default strategy, selected budget or
recommended weight. Every price shock must come from a named supplied scenario
or a separately labeled analyst assumption. With no shocks, retain the symbolic
relation and capability comparison; do not invent a common numerical shock grid.

The exposure model is explicit per sleeve; it is never inferred from a name.
Use `unknown` when it is not declared. Use `not_applicable` when a price reference
is inapplicable, such as domestic nominal cash in an equity-price comparison. That
produces no price-shock numbers, not a claim of zero cash risk or zero total return.
Cash interest, withdrawal timing and inflation belong in separate explicitly
parameterized comparisons; use `planning.cash_projection` for the dated cash model.
Do not force a constant rate, contribution schedule or cash reservation from an
ambiguous field. Preserve the user's assumptions before any supplemental model.

Do not manufacture primary full-budget boundary portfolios, reserve amounts or
arbitrary share quantities merely to make the sleeve table numeric. User-specified
allocations and named trade/cash scenarios remain separate calculations. Primary
comparisons must agree on roles, supplied scenarios, units and scope before their
numbers can be meaningfully compared. Numerical agreement across differing scenarios
is neither expected nor evidence of correct interpretation.

## Operation contracts

Both operations take a `document` with `currency` and `role` equal to
`supplied_observation`, `hypothetical_scenario` or `user_assumption`.

`planning.input_roles` takes `records` with unique `id`, optional `value`,
`source_role` (the three roles above or `unknown`) and `semantic_role`
(`observation`, `maximum`, `minimum`, `target`, `pending`, `scenario`, `unknown`).
Missing source/semantic roles stay `unknown`. Missing value, null value and supplied
empty list are distinct. Pending records optionally declare `pending_state`:
`unknown`, `reserved`, `open_position`, `proposed` or `cancelled`.

Optional `checks` have unique `id`, `constraint_id` naming a maximum/minimum/target
record and a `candidate` object. Both operands need `value`, `metric`, `unit`,
`scope` and `basis`. Missing metadata yields unresolved comparison; mismatched
metadata yields incomparable. For example, an after-cost planned loss of `8.20`
and an after-cost maximum of `12.75` in the same currency and position scope satisfy
`le`; they are not conflicting equalities. Targets use exact equality, without
an implicit tolerance. These checks do not infer quantities or rank candidates.

`planning.reference_comparison` takes ordered `sleeves` with unique `id` and
optional `exposure_model`: `long_linear_price`, `not_applicable` or `unknown`.
Optional `allocation_record`, `holdings_record` and `return_observations_record`
use the record contract above; holdings/returns values must be lists or null.
Only an allocation explicitly declared as a supplied observation with semantic role
`observation` is surfaced as `observed_allocation`. No sum, feasibility or portfolio
normalization is inferred. Nonempty return rows merely establish supplied rows,
not adequate data for a backtest or a validated performance estimate.

Optional `shocks` contain unique `id` and `return_fraction` at least `-1`, matching
the unlevered long linear price reference. No upper bound is imposed. Price P&L per
currency unit equals the supplied return exactly, before costs, yield, flows or tax.
Complete input documents, assumptions and declared roles are retained. Bind their
source references using the normal workflow; these helpers do not read source files,
infer prose intent, authenticate records or create execution gates.
