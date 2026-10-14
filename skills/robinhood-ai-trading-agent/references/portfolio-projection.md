# Dated portfolio and tax scenarios

Keep a present snapshot and a future conditional projection separate. A future
vest, sale or transfer does not increase present cash. Carry every supplied
intervening obligation into the relevant dated projection, or disclose its explicit
exclusion. Do not compare a future numerator to a present denominator. A tax
earmark remains an asset; an actual tax payment reduces assets. Neither helper
establishes tax law, account truth, execution permission or intraday liquidity.

## Bind the whole supplied portfolio context first

When the source contains `baseline_rebalance`, `confirmed_cash_events`,
`withdrawal` and/or `employer.grant_records`, use `planning.source_projection`
instead of hand-selecting its cash flows. Pass `currency`, `role`, the entire
`source`, `source_ref` (file plus `#` prefix), `source_role`,
`date_basis: "source_calendar_label"`, `target_date`, `included_states`,
`mark_policy`, explicit `opening_tax_reserve` (null if unknown), and `liabilities`
(null if unknown). This declared date policy preserves each supplied timestamp's
calendar label for end-of-date accounting; it is not a settlement-time conversion.
The adapter binds opening holdings/cash, every signed confirmed cash event, the
planned withdrawal, and every grant net of withheld/sold tax shares. Events beyond
the target and states not selected remain in the audit. Missing grant deductions
make retained units unknown. Future grants never become cash automatically.

Optional `marks` use the dated helper contract. With explicit
`carry_forward_supplied`, missing overrides use the opening prices; vest-price
assumptions are not silently converted into target marks. `scenario_flows` supplies
separate explicit sale, buy, reserve or tax-payment scenarios using the same source
row contract; it cannot duplicate an automatically bound source flow. Proposed
instructions and recurring contributions remain listed as unmodeled source
sections until their scheduling/fill assumptions are expressly supplied.

`other_assets` is an explicit ledger or null. Alternatively the explicit sensitivity
`residual_policy: "carry_opening_reconciliation_difference"` carries the nonnegative
opening equity less identified assets as an unclassified asset under the selected
mark policy. It does not classify that residual or imply zero liabilities. Without
that assumption or a supplied ledger, complete account equity remains unknown.
An explicit empty liabilities ledger is an assumption/declaration, never a default.

Use `planning.source_alternatives` for multiple diversification or withdrawal
paths on this same common projection document. Supply `alternatives` as
`[{id, scenario_flows}]`; individual alternatives cannot change the target date,
marks, residual treatment or liabilities. It calculates each post-flow asset
weight, supplied target drift, and known employer look-through exposure on its
own post-flow net equity. The unknown residual can contain employer exposure;
known exposure is not labeled complete. Identified-assets denominator results are
separate labeled sensitivities. No preferred lot, issuer objective or weights are
invented. A tax earmark remains in assets; a tax payment is a separate flow.

Both operations require `currency` and `role` (`supplied_observation`,
`hypothetical_scenario`, `user_assumption`). Each source row described below needs
matching `currency`, nonempty `source_ref`, and `source_role` (those three roles or
`unknown`). Source references and the entire input are retained; authenticity is
unchecked. These are declarations to bind to the supplied source through the normal
workflow, not a substitute for source inspection. Decimal arithmetic returns strings.

## Conditional tax sensitivity

`planning.tax_sensitivity` takes a `document` with `scenarios`, a list of
unique-ID source rows with `as_of` (YYYY-MM-DD), `gross_proceeds`, `selling_costs`,
`cost_basis` (total basis for this sold quantity), `tax_rate` (fraction from 0 to 1),
and `selling_costs_reduce_gain` (`yes`, `no`, or `unknown`). Numeric amounts are
nonnegative; absent or null numeric inputs remain unknown. No default rate,
jurisdiction, holding-period treatment, lot method or cost treatment is inferred.

For explicitly supplied gain treatment, the formulas are:

- `net_sale_proceeds = gross_proceeds - selling_costs`.
- Gain with treatment `yes` is `gross_proceeds - cost_basis - selling_costs`.
- Gain with treatment `no` is `gross_proceeds - cost_basis`.
- `positive_tax_estimate = max(0, gain) * tax_rate` only with complete inputs.
- Cash after a hypothetical earmark is `net_sale_proceeds - positive_tax_estimate`.

Selling costs reduce cash proceeds once. Their permitted reduction of gain changes
the tax base; it is not another cash cost. Preserve gross-gain and net-cost-gain
sensitivities as distinct, named scenarios if the source requests both. Unknown
cost treatment keeps tax unresolved, even when the supplied rate happens to be
zero. Negative gains produce no automatic cash loss credit. The helper does not
aggregate taxable gains, offset other income, determine tax liability or record a
payment. A positive estimate is an earmark sensitivity only.

## Dated asset and cash projection

`planning.dated_projection` takes a `document` with:

- `opening`: a source object with `as_of`, `cash`, `tax_reserve`, and explicit
  `positions: [{id, quantity}]`. Positions are long, with nonnegative units. Cash,
  reserve or quantity can be null to retain uncertainty. Missing positions is an
  error; an explicit empty list is a declaration with its supplied source role.
- `target_date`, on or after the opening date.
- `included_states`: explicit subset of `confirmed`, `planned`, `scenario`, even
  if empty. A state of `unknown` can never be selected. Inclusion remains conditional
  and does not establish the event will happen.
- `flows`: explicit list of source rows, each with unique `id`, `date`, `state`
  (`confirmed`, `planned`, `scenario`, `unknown`), `kind`, and
  `included_in_opening: false`. Every supplied flow must be strictly after opening;
  otherwise it risks double counting and is rejected. Events after target or in
  unselected states are explicitly listed in `excluded_supplied_flows`, including
  omitted obligations. No supplied flow disappears silently.
- `marks`: list of source rows with unique `id`, unique `asset_id`, `as_of` and
  `price` (nonnegative or null). No mark may be after target. A single target
  valuation basis is allowed per asset; use separate documents for sensitivities.
- `mark_policy`: `target_date_only` or `carry_forward_supplied`. The first requires
  a supplied mark dated at target for each nonzero holding. The second explicitly
  permits older marks and labels them carried-forward assumptions without any return
  forecast. Missing marks or quantities keep asset totals unknown, while independently
  known cash can still be shown. A zero holding needs no mark.
- `other_assets` and `liabilities`: source valuation rows with unique `id`, `as_of`
  and nonnegative `amount`, under the same target-date/explicit-carry-forward policy
  as marks. An explicit empty list declares none; an absent/null ledger remains
  unknown. Other assets retain an explicitly supplied unclassified residual without
  assigning it to securities or cash. Liabilities are supplied **target balances**;
  no payment or obligation silently adjusts them. Supply reconciled target balances
  when an included payment also settles a liability, to avoid double counting.

All dates are exact YYYY-MM-DD calendar labels for end-of-date snapshots. Mixing
timestamps and dates is rejected. Same-day deltas are aggregated before reporting a
balance, with no invented intraday sequence, settlement availability or minimum
cash claim. Use the separate cash-planning timing contract for those questions.

Flow kinds and their fields:

| Kind | Fields | Accounting effect |
|---|---|---|
| `cash_credit` | nonnegative `amount` | Add cash only |
| `cash_debit`, `external_obligation` | nonnegative `amount` | Subtract cash only |
| `reserve_change` | signed `amount` | Change tax earmark; cash and assets unchanged |
| `tax_payment` | nonnegative `amount`, explicit nonnegative `reserve_release` | Subtract payment from cash and release only the supplied part of an existing earmark |
| `vest` | `asset_id`, nonnegative `quantity` | Add asset units; never assume sale or cash |
| `trade` | `asset_id`, `trade` object | Buy/sell units and debit/credit cash through the existing trade-cost helper |

An unknown flow amount propagates to its affected balance. A missing tax-payment
reserve release leaves the reserve unresolved, even when payment cash is known;
explicit zero means no release. Releases cannot exceed the payment or known reserve.
Tax reserves may exceed cash: negative cash after earmark shows an unfunded scenario,
not borrowing permission. A sale cannot exceed known long units at end of date.

The `trade` object is the existing `planning.trade_costs` one-transaction contract:
`side`, `price`, `quantity`, `entry_orders`, `costs`, and for sales
`transaction_phase` (`entry` or `exit`). The misleading historical field name
`entry_orders` means the order count for the single transaction here. Cost rows
retain explicit units and phases; an explicit empty list is zero modeled costs,
whereas absent/null costs makes trade cash unknown. `exit_price`, `budget` and
`required_net_proceeds` are disallowed here; size quantities through the existing
helper separately. No duplicate sizing engine exists in this module.

`cash_after_tax_earmark = cash - tax_reserve`, while
`identified_assets = cash + total_position_value`,
`total_assets = identified_assets + other_assets_value`, and
`net_equity = total_assets - total_liabilities`. Missing ledgers keep the affected
denominator unknown. Unclassified residuals remain visible separately; no holdings
are invented and no portfolio is renormalized to erase a supplied mismatch. A sale
at the target mark transfers securities into cash and reduces assets only by its
costs; withdrawals and paid obligations reduce the post-flow denominator. Use this
post-flow denominator when comparing post-flow weights, never the opening total.
`timeline` shows dated cash, earmarks, units and applied effects; `flow_audit` retains
every supplied flow and exclusion reason. Future marks, future obligations and
complete holdings are never invented. Reconcile the projected ledger to every
supplied fact before using a denominator or concentration calculation.
