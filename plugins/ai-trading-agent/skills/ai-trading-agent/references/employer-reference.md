# Employer diversification comparative reference

Use `planning.employer_diversification_baseline` for a source-backed employer-stock
comparison before selecting additional user scenarios. This composes the installed
source projection, dated alternative comparison and transaction-cost operations.
It supplies stable research references, not an optimized choice or execution gate.

Its `document` requires `currency`, `role`, `source_ref` (file plus `#` prefix),
`source_role`, `source_utf8` (the complete original UTF-8 source text) and
`source_sha256` (SHA-256 of those exact UTF-8 bytes). Read the original bytes and
decode UTF-8 without normalizing line endings. The adapter verifies the digest,
parses the source and checks its currency. An optional `source` object must equal
the parsed original. A checked digest binds original bytes; it does not authenticate
account information. Retain the original source and operation output for replay.

The supported source schema is the portfolio context: `as_of`,
`baseline_rebalance.{holdings,prices,cash,equity}`, `employer.{symbol,
current_vested_quantity,grant_records,salary_dependency,tax_rate_assumptions}`,
`confirmed_cash_events`, `withdrawal`, `cost_assumptions`, identities, funds and
tax lots. Missing source holdings are not replaced by current employer units.
Conflicting employer/current holding quantities make direct units unresolved,
with both observations retained in the original source. Costs come only from
`cost_assumptions.fee_per_trade` and `one_way_slippage_bps`, as currency per one
hypothetical transaction and one-way basis points. A missing cost component makes
sale cash unknown; it is not zero.

Opening is the original `as_of` calendar label. An optional user-bound
`opening_date` requires `opening_date_role: "user_assumption"` and a nonempty
`opening_date_basis`; carrying opening source balances to that date is explicitly
an assumption. Existing source events must still be after opening: the operation
will not invent an updated opening ledger or double-count already vested grants.
The target is the latest included supplied future vest date. Included states
default to `confirmed`, `planned`, `scenario` as the declared conditional reference
convention; an explicit `included_states` list can restrict them, and every excluded
source event remains in the nested flow audit. Selecting no future vest returns
an unresolved reference-date status and a separate retained projection; no sale
date is invented.

The operation binds `projection_scope: {"mode": "baseline_continuation"}` internally
for every reference and denominator sensitivity, including the retained projection.
Callers need not supply this field. If supplied, it must equal that exact scope;
an independent opening/event scope is rejected. Source events remain in the audit
and undergo the declared date/state filters. Additional independent scenarios use
`planning.source_alternatives` with their own explicit scope; they do not redefine
these fixed references. The lower-level explicit-scope requirement remains in force.

The source `baseline_rebalance.equity` is total account equity, including the
separately listed cash. Reconcile it against marked holdings plus that cash once;
do not add cash to the declared equity again. Keep total account equity/NAV,
identified assets, and any explicitly defined noncash sleeve denominator distinct.
A reconciliation residual is unclassified, not additional cash or established
employer exposure. The named residual sensitivity carries it as an unknown asset
classification; the primary result does not invent missing account balances.

The ordered reference paths are:

1. Retain opening direct units and all included net grants.
2. Sell all net retained units from each included grant on its supplied vest date.
3. Sell opening direct units on the first included supplied vest date and sell all
   included net grants on their supplied vest dates.

These dates are end-of-date accounting conventions, not recommended delays or
claims that shares are immediately saleable. Grant net units are gross shares
less both withheld and sold tax shares; missing deductions remain unknown. Each
positive net grant and the positive opening direct position is modeled as one
separate hypothetical sale transaction. Thus a direct sale and vest sale on the
same date carry separate supplied fees. Zero units create no sale transaction.
All source obligations and withdrawals remain in every path, including negative
cash at earlier dates. Future proceeds never erase earlier unfunded demands.

The primary no-price-change reference uses opening marks for both future position
values and every sale price. This is an explicit shared assumption without a return
forecast. The operation also preserves each source grant's separate vest-price,
gross valuation and net valuation. Its separately named
`source_vest_price_sale_sensitivity` uses those prices only for the corresponding
net-grant sales; direct sale prices and target holding marks remain the same
opening-mark convention. Neither sensitivity is silently substituted for the
primary reference.

Primary prior tax reserve comes from an explicit `baseline_rebalance.tax_reserve`;
primary `other_assets` and `liabilities` come from explicit source ledgers with the
existing dated projection source-row contract. Absent fields stay null. Identified
assets, complete equity and cash after earmark are distinct. Sale-tax amounts stay
unknown because tax-lot selection, selling-cost gain treatment and payment/earmark
instructions are not automatically inferred from supplied tax-rate assumptions.
The operation preserves source tax lots/rates and employment dependence separately.
Known grant tax-share dispositions are not final tax adequacy or a tax-free path.

Each price reference includes a named, explicitly nonprimary
`carry_residual_no_liabilities_no_prior_tax_reserve` denominator sensitivity. It
carries the nonnegative opening equity less identified assets as unclassified
assets and assumes zero target liabilities and zero prior tax earmark solely for
that sensitivity. These assumptions are common across all paths on the same
target date. Unknown discretionary-sale taxes are still unpaid/unearmarked, so
values remain before those unknown taxes. A negative residual is unresolved,
never fabricated as a positive asset. Employer exposure within any unclassified
residual remains unknown; the known employer numerator is not complete exposure.

Compare the returned dated weights, target drift, known employer overlap, cash,
equity and flow audits on their declared common conventions. `selected_alternative`
and objective weights remain null. Additional user-chosen sale quantities, timing,
tax scenarios or reinvestments belong in separate named operations. Preserve prior
substantive differences as unresolved; a new common reference does not retrospectively
make earlier different projections independently reproducible or numerically equal.
