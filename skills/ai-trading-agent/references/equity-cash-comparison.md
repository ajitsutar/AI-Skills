# Same-capital equity and cash comparison

Use `financial.equity_cash_comparison` /
`equity_cash_comparison.equity_cash_comparison(document)` to compare conditional
terminal equity scenarios with cash for the same exact entry/exit interval. The
adapter calls the existing `financial_alignment.price_scenarios` and
`planning_alignment.cash_projection` helpers. It adds no selector, permission,
approval or execution condition.

The schema-1 document has `equity_document` containing the complete existing
price-scenarios argument object and `cash_document` containing the existing cash
projection conventions and endpoints. Each needs explicit currency, role and
nonempty provenance. Currencies and the exact entry/start and exit/end timestamps
must match; do not substitute session close for the requested buffered exit.
This comparison has one initial equity share as its capital basis. A quantity
other than one is unsupported, rather than silently discarded.

The cash opening principal is **derived automatically** from the equity helper's
`entry_outlay_per_share`, including modeled entry costs. Omit `opening_cash` in
the cash input; a supplied value must equal that computed outlay. A stock's quoted
price is a different capital amount when entry costs are nonzero. The derived
cash principal and comparison always have `hypothetical_scenario` role, even if
the rate observations originate in supplied data. Never describe the derived
principal as a supplied observation or existing account balance.

Cash requires explicit `annual_effective_rate`, `day_count`, `floor`, `events` and
`fee`. Missing/null conventions or fee leave cash unresolved; they are never zero
defaults. Only the projection helper's ACT/365F convention is supported. For this
counterfactual, supply `events: []`; external deposits/withdrawals invalidate a
same-capital endpoint comparison and remain unresolved. A positive declared fee
requires `fee_at` within the interval and is passed as a fee withdrawal to the
existing helper. A supplied zero fee adds no event. Preserve original rate, tax,
instrument and other comparator metadata in the cash document; unknown guarantee,
insurance or counterparty terms remain unknown. A cash return model cannot
establish principal assurance.

Terminal-price applicability is separate from arithmetic. Optional timing evidence
uses the **complete original** `source_utf8`, its exact UTF-8 `source_sha256`,
`source_ref`, and explicit `source_role`, plus `terminal_time_pointer` and
`terminal_price_pointers`. The time pointer may be a common RFC6901 pointer or a
mapping from scenario IDs to pointers; price pointers map each scenario ID to its
corresponding price. Time and price must be sibling fields in the same source
scenario or price-bridge record. An unrelated exchange-calendar close, information
cutoff or event timestamp is not a terminal-price bridge. Prices must match the
computed inputs and timestamps must match the requested exact exit.

Omitted/null pointers, absent source timing or mismatched timing leave
`terminal_applicability: UNRESOLVED` and `primary_comparison: null`. The separately
computed `conditional_price_sensitivity` may transfer supplied prices to the
requested exit as an explicitly labeled hypothetical assumption. It cannot turn
an unbound or mismatched terminal value into a primary observation. Even matched
source scenario timing authenticates neither the source nor a future outcome.

Output retains the input, derived cash document, existing equity/cash results,
source hashes, timing/price receipts, unknown cash conventions and comparison
rows. Rows include equity proceeds/return, same-capital cash endpoint/return,
percentage-point excess and terminal-dollar difference. The cash dollar endpoint
uses the after-entry-cost principal; rate comparisons are independent of changing
the capital scale, but dollar balances are not. Both observed and assumed inputs
keep their original provenance and limitations.
