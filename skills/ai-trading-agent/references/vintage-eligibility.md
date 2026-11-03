# Historical value eligibility

Use this contract when auditing historical statements, estimates, revised prices
or per-share values. A period end, event date, membership effective date, split
date or retrieval time does not establish when a value was first public.

For **each exact value and definition**, retain its source row/pointer, instrument
and fiscal period, accounting/adjustment/share basis, first publication, next
superseding publication, and any separately supported basis start/end. A source's
unmapped availability list does not date every field. Two providers with different
periods, GAAP/adjusted definitions or units are not an estimate revision pair.
Without actual analyst estimate vintages, report that coverage as missing.

The eligible interval is the intersection of publication eligibility and the
value's applicable basis interval. Never describe an original value as usable
on *any date before an amendment*: dates before its first publication are out.
Likewise a pre-split value is not available for the entire pre-split history.
A later published recast is not retroactively known on the split date.

With exact source-supported instants, publication eligibility is
`first_publication <= cutoff < superseded_at`. With date-only releases, report
the first-publication day and supersession day as unresolved, the earlier dates
as unavailable, and only dates strictly between those days as conditionally
eligible. After a date-only release day, the value is only the latest **supplied**
vintage, conditional on a common calendar and no omitted intervening revision.
Do not invent midnight, an offset or an event timestamp to run a strict helper.
Retain exact source precision. If source dates do not share an established
calendar, a calendar-order illustration remains conditional; do not certify an
instant or a trading session from it. A known publication time can resolve a
same-day decision only when its timezone and the decision time are known.

Keep the report's final eligible-date table as bounded and qualified as its body.
For each exact value show the unavailable pre-publication interval, ambiguous
boundary days, conditional interior interval, and superseded/out-of-basis range.
State empty intersections explicitly. Membership coverage, delistings/terminal
returns, action accounting, publication coverage and provider adjustment vintages
are separate gates; correct split arithmetic does not make a historical dataset
point-in-time complete. [Audit terminal-return coverage](terminal-return-coverage.md)
before including or excluding the event: a series endpoint does not establish
embedding. Preserve the supplied event, apply once if coverage proves it absent,
do not reapply if coverage proves it already included, and leave unknown coverage
unresolved. Avoid both omission and double counting in the final report.

## Supported offline bounds check

`data.vintage_eligibility` is a workbench/source-bound workflow operation backed
by `scripts/vintage_eligibility.py`. Use `inputs: {"document": {...}}` with exactly:

| Field | Contract |
|---|---|
| `value_id` | Nonempty identity of this exact value/basis, not an aggregate of revisions |
| `source_ref` | Nonempty retained source file/row/pointer; inert text, not authenticated by the helper |
| `precision` | `date` or `timestamp`; all supplied bounds and cutoff share it |
| `as_of` | Cutoff as `YYYY-MM-DD` or an offset-aware RFC3339 timestamp with seconds |
| `first_publication` | First release of this exact value/basis, or null if missing |
| `superseded_at` | Next supplied release that supersedes this exact value, or null if absent |
| `basis_from` | Explicitly declared inclusive basis start, or null if absent |
| `basis_until` | Explicitly declared exclusive basis end, or null if absent |

Basis date conventions are explicit caller assertions, unlike uncertain
publication times. Do not infer a basis boundary from a split date when the
source's effective convention is unknown. Mixed date/instant precision is
rejected; retain the mixed evidence and audit its unresolved bounds separately
rather than discarding precision or manufacturing times for this interface.
Null publication is unresolved. Null upper/basis bounds mean no such constraint
was supplied, not proof of an unlimited window or applicable share basis.
Any violated constraint returns `INELIGIBLE`; otherwise an unknown publication
boundary returns `UNRESOLVED`; only satisfaction of supplied constraints returns
`CONDITIONAL_ELIGIBLE`. All constraints remain visible, including unresolved ones
when another constraint proves ineligibility. No result certifies data readiness.

See [the example](../examples/vintage-eligibility.json). Run the operation for
the source's boundary/interior dates needed by the requested audit, bind its
inputs to the retained source with `research_workflow.py`, and retain helper
results plus normal workflow verification/summary. If boundary conventions must
be illustrative assumptions, label them in the binding and report; do not turn
them into source facts. This helper checks ordering only, without currency,
financial units, price transformations, downloads, inferred timezone or a backend.

The existing `data.asof_snapshot` remains a timestamp-only observation selector.
Use it only when its required instrument, field, event time, availability time,
unit, currency and revision metadata are source-supported. Missing metadata is
a reason to retain a partial audit, not to fill requirements with invented facts.
