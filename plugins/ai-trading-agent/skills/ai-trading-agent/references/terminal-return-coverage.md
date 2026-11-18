# Include terminal returns exactly once

Preserve every supplied delisting or terminal event and its value, identifier,
definition, source and availability evidence. Do not drop a delisted security
from a historical universe merely because current quotes disappeared. A supplied
terminal return is a component to reconcile, not proof of a complete return path.

**A price/return series ending on the delisting date does not establish that it
includes the terminal return.** Neither a final date, an adjusted-price label,
membership removal nor the absence of later rows determines event coverage.
Verify provider methodology or event-specific reconciliation for that exact
series, instrument and event. Preserve the following three-way distinction in
the final recommendation/table, not only in an earlier caveat:

| Evidence for the terminal event in this series | Treatment |
|---|---|
| Already embedded | Retain the event and evidence; do not apply its return again |
| Not embedded | Retain it and include it once separately with compatible return definitions |
| Unknown, conflicting, or no series supplied | Retain the event; leave inclusion/reconciliation unresolved; do not silently omit or add it |

If an event value is missing, never assume zero or a total loss. If coverage
shows it is absent but its value is missing, a complete event-inclusive return
cannot be computed. If evidence shows it is already embedded, do not reapply it
even when the separate event amount is unavailable; disclose that the event's
standalone value is unknown. A zero supplied return is a value, distinct from null.

Including an event separately does not mean arithmetically adding percentages.
When the source establishes successive nonoverlapping simple-return components
with compatible denominators, combine their growth factors. Otherwise retain
separate components and unresolved composition. Do not infer proceeds or write a
full backtest when prices, positions, settlement or denominator evidence is absent.
Point-in-time availability and event coverage are separate checks; retain the
[publication/basis bounds](vintage-eligibility.md) for historical decisions.

## Source-bound coverage operation

Use `data.terminal_return_coverage` through `research_workflow.py` with
`inputs: {"document": {...}}`. The pure helper is
`scripts/terminal_return_coverage.py`; the [example](../examples/terminal-return-coverage.json)
illustrates a supplied terminal event whose return-series coverage is unknown.

| Required field | Contract |
|---|---|
| `event_id` | Stable nonempty identity of the exact event being audited |
| `event_source_ref` | Retained source row/pointer for the event; inert text |
| `terminal_return` | Finite simple-return fraction >= -1, or null; no boolean or percentage-unit inference |
| `series_id` | Identity of the exact series/version, or null when absent |
| `series_coverage` | `embedded`, `not_embedded`, or `unknown` |
| `coverage_evidence` | Array of `{source_ref, kind}`; `kind` is `provider_methodology` or `event_reconciliation` |

Known coverage requires a named series and nonempty explicit evidence. Bind
actual event-specific coverage declarations to retained source bytes; don't
promote a source's final price date into a declaration of embedding, fabricate
an evidence pointer, or use one provider's methodology for another series.
Contradictory or incomplete evidence maps to `unknown` with the reasons retained
in the report. `coverage_evidence` is an assertion to review, not authenticated
by the helper. It intentionally accepts no endpoint-date shortcut.

The output retains the original terminal value even when the action is
unresolved. `additional_application_count` is 0 for already embedded, 1 for
not embedded with a supplied value, and null when unresolved. This is a
conditional audit decision, not an applied ledger, permission to trade or a
computed total return. `combined_return` stays null. Retain the helper result
and normal workflow verification/summary; clearly distinguish supplied facts,
coverage evidence and assumptions.

The existing `backtest.holdings_ledger` remains a different workflow: it uses
unadjusted marks and explicitly confirmed terminal cash entitlements. Do not
translate a return fraction into its required cash-per-unit value without
source-supported denominators, or use it merely to force an audit into a replay.
