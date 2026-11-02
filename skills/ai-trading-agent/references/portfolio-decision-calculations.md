# Budget sizing, price friction and source-bound allocation context

## Scoped conclusion facts

`budget_sizing` adds `conclusion_facts` to each scenario row and, in portfolio
mode, its `portfolio_totals`. `allocation_context` includes a top-level
`conclusion_facts`. Facts carry values, units and result-relative pointers.
Use these with their scenario and scope when writing the final conclusion.
Requested budget, gross exposure, entry costs and outside cash are separate
amounts; unresolved accounting stays unresolved. Alternative rows are not additive.
Known issuer counts describe supplied coverage, with a nullable total when
coverage is incomplete. They do not establish comparative breadth, correlation,
risk ranking or investment dominance. Allocation denominator differences are
not inferred cash. These summaries preserve helper limitations; they do not
validate arbitrary prose or determine a preferred investment.

## Final recommendation context from original sources

`recommendation_report.recommendation_context(document)` (workbench:
`planning.recommendation_context`) binds final recommendation evidence to original
UTF-8 JSON bytes and computed output. Its document has:

- `schema_version: 1`, `currency`, `role`, and explicit
  `deadline_mode: fixed_exit|flexible_review|comparison`.
- `sources: {id: {text, sha256}}`, where hashes cover exact UTF-8 text; duplicate
  JSON keys/nonfinite values are rejected and bytes hashes checked.
- `bindings: {name: {source_id, pointer}}`, with RFC6901 pointers. Bind
  `security_rows` to original rows, and `allocation` to the complete computed
  `planning.allocate` output. Without an allocation, bind `selected_symbols` to
  an explicit retained nonempty selection; quantities/denominator then stay unknown.
- Optional bindings `ranking`, `hard_exit`, `scenarios`, `cash_benchmark`,
  `adverse_thesis`, `exit_plan`. Unbound/absent fields remain explicit unknowns.
- `row_mapping` maps fields to relative JSON pointers in every original row:
  required `symbol`; optional `issuer_id`, `sector`, `industry`, `instrument_type`,
  `period`, `lookthrough`, `dollar_volume_amount`, `dollar_volume_currency`,
  `dollar_volume_period`. Map every supplied material classification/volume field;
  do not omit a known adverse observation to make the output appear unresolved.
- Absent instrument type remains `unknown`. Optional
  `row_assumptions: {instrument_type: {value: equity|fund|cash|other|unknown, basis: ...}}`
  may fill only an absent type as an explicitly declared assumption; the per-row
  receipt retains that assumption separately from source fields. It cannot replace
  a supplied conflicting type. A stock-only premise must be declared rather than
  inferred silently from the profile or symbols.
- When monetary volume is mapped, supply `dollar_volume_unit` using the existing
  context units and `dollar_volume_unit_basis` identifying its source or explicit
  assumption. Do not convert share volume into monetary volume without a retained
  supported calculation. A monetary unit alone does not establish average-period
  semantics; retain those source terms explicitly.

The report calls the existing allocation-context arithmetic with reference gross
notionals and the original allocation-budget denominator, separately for each
single-stock alternative. It returns full source hashes, bindings, mapped row
receipts, source liquidity, issuer/sector/industry exposures and unchanged ranking,
scenario/cash/exit evidence. No new forecast or concentration limit is chosen.
Its interpretation makes scenario losses unbounded by the supplied scenario table,
fixed-sale gap/halt/buyer risk, unknown cash-guarantee terms and missing review/exit
plans visible. Suggested review topics are advice, not sourced events or automatic
sell instructions. Supplied review plans remain unauthenticated declarations.

Present the relevant context alongside the final dollar/selection proposal. A
successful report is not proof of adequate source mapping, an investment approval,
cash affordability, executable liquidity or broker submission.

Standalone: `python scripts/recommendation_report.py retained-context-input.json`.

These pure local calculations take `inputs={"document":D}` through the workbench.
They accept supplied observations or clearly labeled assumptions, produce advisory
research facts, and add no permission checks, broker capabilities or execution
conditions. None selects securities, weights, a fee schedule, a liquidity cutoff,
a price-reference convention or a quantity increment for the caller.

All documents require `currency` and `role`, where role is
`supplied_observation`, `hypothetical_scenario` or `user_assumption`. Numeric fields
accept finite numbers or decimal strings. Nonnegative long notionals and buy
budgets are supported; signed short positions are outside this contract. Decimal
results serialize as strings. Results retain the entire input, an input digest,
sources as supplied and an explicit non-authentication statement. A digest does
not establish the source's accuracy or freshness.

## Explicit budget sizing

For a supplied `cost_assumptions` object containing `fee_per_trade` and
`one_way_slippage_bps`, use `planning.source_budget_sizing` /
`portfolio_decision.source_budget_sizing(document)`. This adapter retains the
whole original source and applies both components to every selected price row.
Do not manually build fee-only rows while calling the result full-cost sizing.

The input contains `schema_version: 1`, the common explicit `currency` and `role`,
and the unchanged `mode`, `budget`, `rows` and `quantity_scenarios` from the budget
contract below. Each row must have a positive integer `entry_orders`; every
quantity scenario must explicitly supply its basis and step. Supply:

```text
cost_source = {text, sha256, role, provenance}
cost_bindings = {cost_assumptions: RFC6901_pointer, currency: RFC6901_pointer}
sensitivities = [{id, price_basis, ?price_reference_description}]  # optional
```

`text` is the complete retained original UTF-8 JSON source, and `sha256` hashes
those exact bytes. Both bindings select fields inside that document. Bind
`currency` to the source's explicit currency; it must match the sizing currency.
The source role is explicit `supplied_observation`, `hypothetical_scenario` or
`user_assumption`, with retained provenance. Do not replace the original source
with a hand-written object containing only the preferred fee. The adapter rejects
unsupported fields in this narrow cost-assumption object; other source schemas
continue to use the low-level helpers with explicit mappings.

The fee maps to a per-order entry cost using the row's explicit order count.
One-way slippage maps to an independent entry `bps_notional` model against that
row's explicit price reference. Missing/null fee or slippage remains unresolved,
including when the other component is known; only a supplied zero is zero. Rows
cannot override these components with their own `costs` or `modeled_slippage`.
A quoted full spread remains an observation and is never added as another charge.
The adapter calls the existing `budget_sizing` and `trade_costs` implementations;
it does not create another quantity algorithm, select names or alter budgets.

Map a sourced stock close to `price_basis: last` explicitly and retain the price
provenance. An unrelated fund quote with unknown basis remains unknown in its
own row; it cannot erase stock slippage. For unknown bases, the primary result
retains both cost components and leaves affordability unresolved. Optional named
sensitivities assume the declared basis only for those unknown rows, with both
costs still applied. Known row bases remain unchanged. For `other`, explicitly
describe the sensitivity reference. Present these as conditional reference-basis
sensitivities, alongside the unresolved primary result, never as observed broker
affordability. A fee-only calculation belongs to a separate explicitly labeled
lower-level diagnostic; it cannot replace this full-source result.

Output includes `primary_result`, separate `sensitivities`, the complete original
`cost_source`, checked byte/canonical hashes, bindings/provenance and `cost_mapping`.
These findings add no execution prerequisite or permission condition.

`planning.budget_sizing` / `portfolio_decision.budget_sizing(document)` requires:

```json
{
  "currency": "USD",
  "role": "hypothetical_scenario",
  "mode": "portfolio",
  "budget": "240",
  "quantity_scenarios": [
    {"id": "whole", "quantity_basis": "whole_shares", "quantity_step": "1"},
    {"id": "fractional", "quantity_basis": "fractional_shares", "quantity_step": "0.01"}
  ],
  "rows": [
    {
      "id": "selected-security",
      "symbol": "SUPPLIED_SYMBOL",
      "budget": "180",
      "price": "17.60",
      "price_basis": "last",
      "entry_orders": 1,
      "costs": [
        {"id": "supplied-entry-fee", "amount": "0.45", "unit": "per_order", "phase": "entry"}
      ],
      "provenance": {"source": "explicit illustrative assumptions"}
    }
  ]
}
```

The numbers, names, increment and costs above are examples, never defaults.
Use the actual selected rows and source amounts. Every row and quantity scenario
has a unique nonempty `id`. `symbol`, `period` and `provenance` are optional retained
metadata. The array order is preserved.

- `mode=portfolio` requires a separate cash `budget` for each row. Their known sum
  cannot exceed the document budget. Unassigned budget remains separate. This
  helper does not choose an equal split or redistribute rounding residuals.
- `mode=alternatives` treats each row as a mutually exclusive use of the entire
  document budget. An optional row budget must match it. There are no aggregate
  alternative totals: those independent debits and notionals must not be summed.
- Each `quantity_scenarios` entry requires `quantity_basis=whole_shares` or
  `fractional_shares` and its own positive `quantity_step`. Whole-share increments
  must be integers. Increments and prices have the same minimum positive value
  supported by `planning.trade_costs` (`0.000000000001`). Fractional scenarios
  describe supplied assumptions, not broker eligibility.
- A row's `costs` uses the existing `planning.trade_costs` array contract:
  `{id,amount,unit,phase}`, with `unit=per_share|per_order|bps_notional|per_round_trip`
  and `phase=entry|exit|each_side|round_trip`. A round-trip charge needs
  `charged_at=entry|exit`. Per-order entry charges need a positive integer
  `entry_orders`. All supplied cost rows remain retained; entry sizing only
  charges costs applicable to entry, including round-trip charges assigned there.
- `costs=[]` explicitly supplies an empty model. Missing or null costs, unknown
  amounts/units/phases, missing relevant order count, null price, null row budget
  or null increment leave the affected quantity and debit unresolved. Missing
  costs never become a claim of observed zero. Known invalid values, contradictory
  cost units/phases, duplicate IDs or incoherent budget sums raise an input error.

For each row and scenario, the implementation calls the **existing budget path**
of `planning_alignment.trade_costs`, then quotes that computed quantity using the
same helper and costs. It returns `quantity`, `gross_notional`,
`modeled_entry_cost`, `modeled_cash_debit`, `budget_remainder` and the underlying
`trade_cost_result`. Zero quantity uses that helper's zero-charge convention.
No second sizing formula is implemented here. Portfolio totals include all
modeled entry costs and the total budget remainder, including unassigned cash;
if any row is unresolved, those aggregate totals remain null. Each scenario is
independent; never add the whole and fractional scenarios together.

The result is a cost-aware cash-budget estimate using only the supplied terms.
It does not estimate omitted taxes, exchange charges, price changes or realized
execution. Use explicitly named separate input jobs for alternative assumptions;
do not put a sensitivity in the primary answer as an observed fee or capability.

## Observational spread and modeled one-way slippage

`planning.friction_context` / `portfolio_decision.friction_context(document)` takes
the common header plus the same row fields accepted by budget sizing:

- `costs`: the existing cost rows described above, excluding the separate
  observational quote and separate one-way slippage model.
- `price_basis`: `midpoint`, `bid`, `ask`, `last`, `other` or `unknown`.
- Optional `quoted_spread`: `{amount,unit,reference_price_basis?,reference_price?,
  period?,provenance?}`. `unit` is `bps` or `price_per_share`; this field always
  means the **full bid-ask spread**. Its reference basis may be unknown. The
  observation is retained as supplied and never added to costs or divided by two.
- Optional `modeled_slippage`: `{id,amount,unit,phase,convention,
  reference_price_basis,overlap,overlapping_cost_ids?,period?,provenance?}`.
  `unit=per_share|bps_notional`, `phase=entry|exit|each_side`,
  `convention=one_way`, and its reference basis must explicitly match the modeled
  price basis. For `other`, both row/document and model must also supply the same
  nonempty `price_reference_description`.
- `overlap=independent` adds the one-way model once to the cost array. It cannot
  list overlapping cost IDs or reuse another cost ID. `overlap=included_in_costs`
  requires the existing `overlapping_cost_ids` containing the modeled effect;
  the model is then retained but no extra charge is added. This inclusion is a
  caller declaration, not independently verified decomposition of a bundled fee.
  The referenced costs must cover every declared slippage phase; an exit-only
  charge cannot contain entry slippage, and exclusively zero charges cannot
  contain a declared positive effect. Inconsistent declarations stay unresolved.
  Missing or `unknown` overlap leaves the primary cost model unresolved.

An absent `modeled_slippage` means none was supplied, not observed zero slippage;
an explicit null model means its amount/applicability is unknown. A supplied model
with unknown/mismatched reference basis or incomplete one-way convention remains
unresolved. A named assumption with an explicit matching basis remains usable
even if an unrelated observed spread's basis is unknown. Currency mismatches are
reported as unresolved; no FX conversion is assumed.

From a midpoint reference, half of a quoted full spread can describe the distance
to one quote side under explicitly chosen assumptions. From an ask reference for
a buy, the quoted crossing can already be embedded in the reference price. A last
trade or unknown reference does not establish either convention. These facts do
not select a convention for a particular input. Supply the intended one-way model
and reference explicitly. Never substitute the full spread for one-way slippage
or add overlapping spread and slippage twice. A cost row explicitly marked
`kind=quoted_full_spread` or `kind=one_way_slippage` is unresolved until mapped to
the corresponding dedicated field; arbitrary fee labels are not semantic proof.

## Source-bound allocation context

`planning.allocation_context` / `portfolio_decision.allocation_context(document)`
takes the common header, a `denominator` object and `rows`:

```text
denominator = {amount, basis, ?period, ?provenance, ?currency}
row = {id, ?symbol, notional, notional_basis, instrument_type,
       ?issuer_id, ?sector, ?industry, ?period, ?provenance,
       ?classification_provenance, ?currency, ?dollar_volume, ?lookthrough}
dollar_volume = {amount, currency, unit, ?period, ?provenance}
lookthrough = {constituents, ?period, ?provenance}
constituent = {id, weight, instrument_type, ?issuer_id, ?sector, ?industry,
               ?period, ?provenance, ?classification_provenance, ?lookthrough}
```

The denominator's positive amount and descriptive `basis` are explicit. Examples
of a basis are account equity, selected-portfolio notional or a supplied sleeve
value; none is substituted for another. If its amount or basis is unknown,
exposure amounts can still be reported but fractions stay null. Monetary values
inherit the document currency unless a row/denominator explicitly supplies a
different one, which remains unresolved. Dollar volume always needs its own
currency to establish compatibility.

Each top-level row's `notional_basis` must explicitly be `gross_notional`.
Cash debit, net sale proceeds and a share quantity are not interchangeable with
gross exposure. Missing values or another/unknown basis leave the row unquantified;
the helper never converts them to zero or performs an implicit quantity-to-dollar
conversion. Bind a quantity and price calculation first when needed. No portfolio
total or denominator difference is asserted while any top-level row is unquantified.

`instrument_type=equity|fund|cash|other|unknown` distinguishes fund expansion and
explicit cash. An omitted type is unknown. For direct equity or other instruments,
only the actual supplied issuer, sector and industry labels enter their respective
groups. A symbol is never substituted for an unknown issuer. Missing labels and
the label `unknown` are recorded as unknown exposure. Cash is non-applicable to
these three concentrations and remains in the declared denominator. An unknown
instrument type leaves its classifications unknown rather than assuming it is a
direct stock. The contract does not identify security aliases or independently
verify that differently spelled issuer IDs are distinct issuers.

`exposures.issuer_id`, `.sector` and `.industry` each contain `groups` with the
notional, fraction of the **original declared denominator**, and source-bound
contributors. Each dimension separately reports known classification amount,
unknown amount, explicit non-applicable cash and unquantified row IDs. A zero
conservation residual checks accounting within the known notionals; it does not
mean classifications, the account or source coverage are complete.
`denominator_difference` is a signed arithmetic difference, not an inferred cash
balance or automatically classified exposure. The helper does not renormalize
known labels to 100%, so unknowns cannot dilute a reported concentration by
silently changing its denominator.

Fund records expand **only supplied constituent weights**. Each weight is a
fraction of that fund (not percent), lies in [0,1], and their known sum cannot
exceed one. Recursive nested fund records use the same contract. Top-level fund
sponsor or fund-sector labels do not become underlying issuer or sector exposure.
Missing holdings, unknown-weight constituents and unsupplied residual weight
remain opaque/unknown. No equal weights or missing constituents are invented.
Different holdings dates, top-level notional provenance and constituent provenance
remain in the contributor source chain;
no synchronization or freshness claim is made. Fund coverage separately reports
known fund notional, terminal nonfund holdings, embedded cash, opaque/uncovered
notional, per-fund source records and unquantified fund rows. An unknown constituent
instrument type is opaque rather than an assumed nonfund holding. The terminal
coverage fraction stays null if any fund notional or constituent weight is unknown,
even when known weights already sum to one; missing weights are not declared zero.
Classification
coverage may be incomplete even when constituent weights are complete.

For each row, `dollar_volume_context` compares gross notional with the supplied
monetary-volume amount only when currencies and units match. Supported units are
`currency_per_day`, `currency_per_session` and `currency_over_period`. The ratio's
units are respectively days, sessions or fraction of period volume. For an
average, put its actual averaging window and observation dates in `period`; no
averaging window is selected by the helper. Share volume, missing currency,
unknown/zero volume or unknown notional yields an unresolved ratio. A negative
volume amount is incoherent arithmetic input. Supplied period, provenance and
units remain in the observation, including explicit metadata-known flags.

The ratio is arithmetic context, not a participation schedule, a claim that the
trade can be filled, a liquidity threshold or a market-impact estimate. Missing
period/provenance is visible and never treated as current evidence. The helper
does not retrieve quotes, infer liquidity cutoffs or impose execution conditions.

## Reporting and composition

Keep the selected set and allocation contract intact. When given explicit cash
budgets, compose budget sizing for the requested quantity scenarios, then bind
the desired scenario's **gross notionals** into allocation context together with
the retained issuer/sector/industry and dollar-volume source fields. Preserve
primary, hypothetical and mutually exclusive alternatives in separate jobs.
Report amount, cost, debit and residual together; include concentration and volume
facts from the same selected rows. Do not claim a context job describes a different
scenario, an entire account when only selected rows were supplied, or an omitted
portfolio alternative. These advisory calculations never authorize or veto an
order.
