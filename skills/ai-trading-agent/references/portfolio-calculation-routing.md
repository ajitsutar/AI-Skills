# Portfolio calculation routing

Read this guide for allocation, budget, exposure, sleeve, dated funding,
employer diversification, withdrawal, recommendation-context and equity/cash
comparisons. The operation-specific source and accounting instructions below
apply when their stated request and input conditions are met.

For allocation amounts without user weights or supported optimizer inputs, use
the [shared allocation baseline](allocation-policy.md) and
`planning.allocate`: equal notionals across the supplied selected set. Preserve an
explicit count and the retained source order; without a count, do not invent one.
Keep an existing reviewed selection intact. A diagnostic queue only supports a
conditional research allocation, not a stronger recommendation label. Scores are
not expected returns or allocation weights. Full-budget single-stock alternatives
are separate scenarios, not amounts to sum into one portfolio. Fees and required
cash-debit sizing remain explicit separate calculations.

For a cash-budget comparison, use `planning.budget_sizing` to compute affordable
whole/fractional quantities, modeled entry costs, total debit and residual together.
When an original source supplies `fee_per_trade` and `one_way_slippage_bps`, use
`planning.source_budget_sizing` with the entire cost source and explicit currency
binding. It preserves both components for every quote; unknown reference bases
remain unresolved beside named complete-cost sensitivities. A fee-only result
must be labeled as a limited sensitivity and cannot replace full-cost affordability.
Keep quoted spread separate from explicit one-way slippage with
`planning.friction_context`. After selecting a scenario, use
`planning.allocation_context` with its gross notionals and the supplied issuer,
sector, industry, fund holdings and dollar-volume records. Report known adverse
facts alongside unknowns; unknown classifications keep the original denominator.
See [portfolio decision calculations](portfolio-decision-calculations.md).
When identity maps, fund holdings or supplemental issuer observations are supplied,
use `planning.source_allocation_context` with their whole source records for every
selected comparison alternative. The [source-exposure guide](source-exposure.md)
defines the supported adapters. It merges all available share-class and constituent
identities before calculating exposure; do not replace this with a hand-built
partial mapping. Available classifications and monetary observations cannot be
called missing because a model omitted them. Qualitative business descriptions do
not establish formal sector/industry labels; retain them separately. Distinguish
complete supplied fund weights from actual issuer diversification, and discuss
material concentration even for a fund labeled broad. Bind gross notionals to the
retained sizing scenario, with cash, costs and the denominator kept separate.

Before a portfolio or sleeve comparison, preserve supplied observations, user
assumptions, scenarios, targets, ceilings and pending states with
`planning.input_roles`. Missing holdings are unknown, not an empty account.
A loss ceiling is an inequality, not a requested loss or sizing target. Use
`planning.reference_comparison` for the shared capability and explicit unit-price
comparison when allocations are absent; do not invent weights or a shock grid.
See [planning input roles](planning-input-roles.md).
For sleeve performance, keep combined returns and blended benchmarks unknown
unless common units, matching periods and non-overlapping coverage are bound to
evidence. Disclosed endpoint fees must not be subtracted twice. Conditional
aggregation and Brinson arithmetic do not establish observed combined performance
or causal investment/execution attribution; use the workbench's retained basis
states and [attribution guidance](quant-workbench.md).

For a supplied portfolio context, use `planning.source_roles` for the loss-basis
and role record, `planning.source_projection` for a complete dated projection,
and `planning.source_alternatives` for comparable post-flow alternatives. Use
`planning.settlement_transfer_sweep` to enumerate sale dates from the supplied
calendar rather than selecting a convenient date before checking the earlier path.
The linked guides define explicit source schemas and mappings; unsupported fields
remain visible as mapping gaps. An unknown loss basis stays unknown even when a
trade-cost example is also supplied.

For future vest, withdrawal or diversification comparisons, use
`planning.dated_projection`: carry supplied intervening flows, explicit marks,
residual assets and liability balances into the same target-date denominator.
Do not use current equity for a post-withdrawal weight. Use
`planning.tax_sensitivity` with explicit cost-basis, rate and selling-cost tax
treatment; unknown treatment stays unknown. Tax earmarks remain assets until paid.
See [dated portfolio projections](portfolio-projection.md).

For employer-stock diversification without user-specified scenario quantities or
prices, start with `planning.employer_diversification_baseline` and the
[shared employer reference](employer-reference.md). Compare retention,
selling net new vests, and selling existing direct shares plus net new vests on
the same comparison date and valuation basis. Its carried opening-price reference is an
explicit no-price-change assumption, not a forecast. Keep source vest-price
sensitivities and other user-chosen paths separate. Missing account facts remain
unknown in the primary result; a common denominator sensitivity never replaces
them. These reference paths establish no preference or recommended sale date.

When several alternatives trade off taxes, liquidity, concentration and allocation,
use `planning.alternative_comparison` with explicit comparable criteria. Without
supplied priorities, present the alternatives and conditional tradeoffs rather than
an invented uniquely optimal choice. Use `planning.settlement_transfer_paths` for
explicit date-only scenarios; same-day settlement and transfer acceptance remain
unknown without a stated assumption. Distinguish transfer initiation from arrival.
For a withdrawal proposal without supplied priorities, honor the
`planning.source_alternatives` proposal contract: present the conditional funding
alternatives and their tradeoffs with no default favorite. Do not silently prefer
liquidity, taxes or concentration on the user's behalf. Use the sweep's
`reference_path` as the shared conditional timing example when available; keep
other timing choices separate. A null reference leaves timing unresolved. This
reference is neither a recommended sale date nor a guarantee. Preserve any
explicit user selection or priority instead of replacing it with the reference.
Use the sweep's `sale_date_summaries` when describing later dates: preserve both
same-day and next-listed-day path statuses. Unknown intraday acceptance and missing
calendar coverage are different facts; a mixed date cannot be labeled wholly
uncovered merely because its later path exceeds the calendar.
See [planning comparisons](planning-comparison.md).
These helpers preserve analytical assumptions and add no execution conditions.

For a selected-stock allocation or fixed-exit recommendation, run
`planning.recommendation_context` against the original security rows and retained
allocation/selection. Carry its exposure, monetary-volume context, source gaps,
scenario-loss interpretation and exit review topics into the answer. Fixed-date
liquidation must address gaps, halts and liquidity; a terminal scenario is not a
loss limit. A modeled cash return does not establish principal-guarantee terms.

For equity scenarios versus cash, use `financial.equity_cash_comparison` and the
[same-capital comparison](equity-cash-comparison.md). It derives the
counterfactual cash principal from equity entry outlay including modeled costs;
the stock quote is not a supplied cash balance. Match the exact holding interval
and declared cash conventions. Missing source-bound terminal timing leaves the
primary comparison unresolved, beside a separately labeled price sensitivity.
An unrelated session close cannot establish a terminal price's timestamp. The
per-share reference is an accounting unit, not a whole-share execution rule.

