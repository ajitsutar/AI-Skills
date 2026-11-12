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

Cash numerical computability and dated benchmark applicability are separate.
Supply document `as_of` (matching the workflow contract cutoff) and `cash_benchmark` with `instrument`, `evidence` (a
nonempty list of source descriptions), `observed_at`, explicit positive integer
`max_age_seconds`, matching `entry_at`/`exit_at`, `rate_or_return`,
`basis: "annual_effective"`, `day_count: "ACT/365F"`, `currency`, and `methodology`.
The rate must match `cash_document.annual_effective_rate`. Existing
`cash_benchmark.review_cash_benchmark` checks the observation against the research
cutoff and caller's freshness policy, exact interval, maturity, and conversion
assumptions. Missing freshness policy is unassessed; do not invent an age limit.
Use `instrument_maturity_at` or explicit `horizon_adjustment_evidence` for a
maturity mismatch, rollover, early sale, or floating cash. A fresh quote need not
guarantee a future rate: constant-rate projection is an explicit assumption, not
proof of a locked yield or a guarantee through the holding period.

Use the source-bound research workflow for dated primary comparison. It derives
`benchmark_provenance` from actual source/assumption bindings; do not supply that
argument in a workflow plan. Primary metadata requires the explicit source role
`supplied_observation` or `supplied_observations`; unknown, scenario or assumption
roles remain conditional. These are source declarations, not authentication. Bind observation time, rate, instrument and currency
to sibling fields in the same retained original quote record or explicit source
bridge, and bind each comparison leg's currency to its supplied evidence. An
exchange-calendar publication date, a research cutoff, assumed timestamp or
assumed currency cannot establish source-confirmed quote applicability. Retain
original source bytes; do not rewrite an undated rate into a newly dated record.
Source bindings prove retained byte lineage, not authenticity or upstream truth.

`cash_calculation_unresolved` concerns arithmetic; `cash_applicability` retains
the separate review, source bindings and missing/stale/future/mismatched reasons.
`cash_unresolved` includes both. Missing cash dates or assumed metadata leave
`primary_comparison: null` even with valid terminal equity timing, while preserving
`cash_result` and conditional rows whenever numerical conventions are complete.
A direct helper call without workflow provenance also remains conditional.
Explicitly report these limitations rather than describing an undated projection
as an appropriately dated benchmark. A passing primary row is still a conditional
scenario comparison, never a forecast or guaranteed cash outcome.

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
