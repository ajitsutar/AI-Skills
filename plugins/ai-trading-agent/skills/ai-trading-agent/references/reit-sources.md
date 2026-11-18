# Original property fractions

`reit_sources.analyze(request, manifest_path, expected_manifest_sha256,
source_root=None)` retains the existing `document` and `bindings` interface.
See `reit-reconciliation.md` for monetary operand binding. Property fractions
can use the same bindings array:

```json
{"target_pointer":"/property_fractions/0/value",
 "schema":"property_disclosure_v1","source_id":"filing",
 "record_pointer":"/portfolio","field":"largest_tenant_revenue_fraction","sign":1}
```

This closed schema recognizes `property_occupancy`,
`largest_tenant_revenue_fraction` and
`net_lease_expirations_next_year_fraction`. The selected original object must
contain the exact field. Its scalar value or same-field object's literal `value`
must equal the requested fraction, lie within zero and one, and be finite.
Unknown fields, alternate numeric siblings, invented trusted flags, negative
signs, duplicate targets and mismatched values are rejected.

The revenue field name establishes only a **broad revenue denominator**. It does
not establish gross/net/rental/GAAP revenue, reporting entity, consolidated scope,
or period. Generic occupancy and lease-expiration fields establish no denominator.
The `next_year` name retains a relative label, not a calendar-year anchor.

An original same-field object may explicitly provide `denominator`,
`denominator_scope` and `time_anchor` alongside `value`. Metadata is never borrowed
from a parent, adjacent field, another fraction or a caller assertion. An explicit
denominator that contradicts the closed field meaning is retained as a source
conflict. Caller conflicts remain separately visible. Unknown metadata stays
unknown; null caller metadata cannot erase a bound original revenue label.
Binding proves this local record association, not financial/source authenticity.

Independently of requested bindings, the helper scans every manifest JSON original
for exact supported field names. It records every occurrence with source ID, hash,
pointer, value, supported meaning and unresolved scope. Identical values and
ambiguous multiple occurrences stay separate. They are never automatically joined
to a requested row by value or ID. Invalid supported fields remain diagnostics;
prose and unsupported formats are not semantically interpreted. The result records
scanned sources and unsupported formats and does not claim complete property
coverage. This diagnostic inventory preserves source-present information even
when the caller omits a binding or the entire property-fraction array.

The deterministic report includes all requested property rows and the independent
original-field inventory. It distinguishes declared values, exact bound fractions,
known broad denominators, unresolved precise scopes/time, and conflicts. The
top-level status reflects unresolved property rows; source-field observations
alone cannot certify comparability, entity identity, tenant safety or lease risk.
The report hash is replayable after relocation of retained original files; it
does not certify arbitrary surrounding prose.
