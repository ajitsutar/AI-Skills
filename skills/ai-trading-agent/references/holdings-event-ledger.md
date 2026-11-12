# Holdings, corporate actions and dated funding

Use `backtest.holdings_ledger` (`holdings_ledger.replay(document)`) for an explicit
long-only, single-currency event scenario. It joins held units and supplied lots,
corporate-action entitlements, settled cash, transaction costs, declared taxes and
withdrawals. It is separate from period-return `backtest.portfolio`: never apply
the same corporate action through both adjusted returns and explicit ledger events.

This operation consumes events; it does not download them, infer tax law, manufacture
historical prices, generate an investment strategy or establish broker buying power.
Source metadata remains caller-supplied. A proposed event sequence is a scenario,
not evidence of executed orders. Missing quantities, basis, tax amounts and market
values remain unknown where the contract allows them.

## Input and event rules

After an action invalidates a security's mark, a replacement mark must have an
observation time at or after that action. A later retrieval of a pre-action price
does not repair its share or entitlement basis. Marks inherit the ledger currency
when omitted; an explicitly conflicting mark currency is rejected.

Required top-level fields: `currency`, timezone-bearing `as_of`,
`price_basis: "unadjusted"`, `valuation_policy: "observed_only"` or
`"allow_references"`, `tax_mode`, `equal_time_order: "supplied_order"`,
`opening`, and ordered `events`. Optional `cash_floor` applies to settled cash
after reserving the declared tax liability. Amounts and quantities use decimal
strings or integers. The module never rounds share units to an assumed broker step.

`opening` supplies `at`, `cash`, optional `tax_liability`, `lots` and `marks`.
Each lot supplies unique `lot_id`, stable caller-mapped `security_id`, `quantity`,
total `basis` (or null) and `acquired_at`. Marks supply security, `price` (or null),
`kind` (`observed`, `reference`, `modeled`), `observed_at`, `available_at` and `source`.
Dates must be available by the event that consumes them. Stable IDs are required
identifiers, not independent certification of the issuer mapping.

Every event supplies unique `id`, `type`, `at`, and `source`. The input order is
explicit for simultaneous events; it is not guessed exchange sequencing.

| Event | Additional fields and behavior |
|---|---|
| `mark` | Same mark fields; nonobserved values require reference-policy opt-in for NAV. |
| `buy` | security, quantity, price, cost, new lot ID, settlement time, `execution_price_basis: "observed"`. Debits all cash at trade time conservatively. |
| `sell`, `cash_in_lieu` | security, quantity, price, cost, explicit ordered lot IDs, settlement time, observed execution basis. Removes units and creates a receivable; no reuse before settlement. |
| `split` | security, positive factor. Preserves total lot basis, changes units, invalidates pre-action mark. |
| `dividend` | security, ordinary/special type, per-unit cash, settlement time. Creates cash entitlement; requires new ex-action mark and does not reinvest automatically. |
| `spinoff` | parent security, distinct child security, positive child ratio, child basis fraction or null. Parent units remain; child units survive a later parent sale. Both require new marks. |
| `merger` | parent, cash per unit, settlement time, confirmed terminal outcome; optional distinct child/ratio and explicit child basis by parent lot. No inferred reorganization tax treatment. |
| `delisting` | confirmed terminal outcome, cash per unit and settlement time. Zero proceeds require the same explicit confirmation as positive proceeds. Unknown outcome is not zero. |
| `tax_accrual`, `tax_payment` | Explicit amount. Payment reduces cash and liability together, avoiding duplicate reserve subtraction. |
| `deposit`, `withdrawal` | Positive amount; withdrawal needs settled unreserved cash above the declared floor. |
| `settlement` | Advances the clock; due receipts also settle before every event and at final cutoff. |

An unquoted child produces unknown full NAV unless an explicitly selected reference
scenario supplies its mark. These marks never qualify as execution prices. Mark dates
are retained; the operation does not independently certify freshness or liquidity.

## Tax and funding interpretation

`tax_mode: "unmodeled"` leaves net-of-tax value unresolved. In
`"explicit_event_amounts"`, each disposal/distribution/action needs its supplied
`tax_amount`, including explicit zero when appropriate. In `"positive_sale_gains"`,
a sale may instead supply a `tax_rate`; it applies only to positive realized gains
after supplied selling costs and basis. No automatic loss benefit, wash-sale,
holding-period classification or state-tax rule is inferred. Other taxable events
still need explicit amounts. Unknown inputs remain in `unresolved_tax_events`.

The additive `tax_evidence` output retains each tax-relevant event's input pointer,
caller source, treatment, amount (or null), source-field pointers and missing inputs.
Pointers are relative to the input document identified by `input_sha256`; a
rate-based sale tax also identifies the computed realized gain with a separate
result pointer. An explicit zero remains a supplied zero. An omitted opening
`tax_liability` uses the documented zero default and is labeled as a default,
not an observed source fact.

`declared_accrual_total` excludes the opening balance; that opening balance plus
accruals minus `declared_payment_total` equals `declared_liability_remaining`.
`total_scenario_liability_remaining` and `unresolved_scenario_liability_amount`
remain null while any tax is unresolved, including unmodeled taxes. Paying all
declared liability does not resolve a missing amount. When the supplied model has
no unresolved taxes, the latter field is zero and the former is the declared
balance; neither verifies actual tax law. `actual_tax_liability_amount` is always
null because this operation never establishes actual tax liability.

Carry `conclusion_facts` into narrative comparisons: a numeric difference in cash
or declared payments across scenarios is a scenario difference, not the amount of
an unresolved liability. Do not describe that difference as unpaid tax merely
because a comparator supplies a tax amount. Identifying missing tax requires
evidence for that same scenario; retain its unknown amount and net-of-tax value
until then. These facts support review of prose but do not automatically validate
arbitrary narrative claims.

The tax reserve remains part of gross cash; the liability is subtracted once to
derive net NAV and available cash. Paying it reduces both cash and liability.
The returned cash/receivable conservation residual must be zero. The timeline
shows whether the supplied sequence actually funds a dated withdrawal, distinct
from a pre-tax target allocation. Purchase settlement is retained, but full purchase
cash is reserved at trade time; this intentionally conservative rule is not a
broker-specific cash-account model.

See `examples/holdings-event-ledger.json` and `tests/test_holdings_ledger.py` for
portable synthetic spin-off, split, merger, dividend, delisting, cash-in-lieu,
unknown-value, settlement and tax-reserve cases. They demonstrate accounting
semantics, not complete historical S&P coverage or real tax outcomes.
