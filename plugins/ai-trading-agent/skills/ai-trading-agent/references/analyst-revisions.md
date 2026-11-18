# Source-bound analyst revision delivery

Use the `ANALYST_REVISIONS` analysis profile in an externally adopted
[source-coverage scope](source-coverage.md) for supplied-source rating, target
and earnings/revenue revision questions. Preserve the complete original request,
literal requested-topic spans and full original source inventory. This is a
native analysis within the actual complete generated Markdown/JSON pair, not an
annex or an authored factual override. Run the existing source_coverage compose
and verify commands; add `"analysis_profile": "ANALYST_REVISIONS"` to the scope
before adopting its SHA256. The plan schema stays unchanged.

The reader scans every original JSON source for root `events` and
`individual_targets` arrays. Supported records contain `firm_id`, `issued_at`
and any of `rating`, `target`, `eps`, `revenue`, with original dimensions such as
`issuer`, `currency`, `price_basis`, `target_horizon`, `fiscal_period`,
`eps_basis`, `unit_revenue` and `revenue_basis`. Numeric fields must be finite
JSON numbers. The reader retains exact source IDs, original JSON pointers,
file hashes and original fields. Unsupported original JSON sources remain
explicit; all original text/JSON stays in the complete source inventory.

When a record has a raw `source` reference, its path must resolve uniquely in
the pinned corpus and its SHA256 must agree. The original raw text is retained.
The optional declared excerpt is checked literally. Narrow first-label matches
for rating/target/EPS/revenue provide explicit raw corroboration status, separate
from structured record origin. A structured field absent from the recognized
raw grammar remains `STRUCTURED_ONLY_RAW_FIELD_UNRESOLVED`; an absent raw
reference remains unavailable. Neither means the structured value was present
in the raw publication. Recognized contradictory numbers/currency remain
conflicts. This is bounded extraction, not source authentication or exhaustive
semantic parsing.

Each metric has its own comparison dimensions:

| Metric | Required comparison dimensions |
| --- | --- |
| Rating | Firm and issuer; original rating labels remain literal, without an inferred ordinal score |
| Target | Firm, issuer, currency, share/price basis and target horizon |
| EPS | Firm, issuer, currency, fiscal period and EPS accounting/share basis |
| Revenue | Firm, issuer, currency, fiscal period and revenue unit; revenue accounting basis is recorded separately |

Do not use missing EPS basis or fiscal period as a reason to reject a target
comparison. An event's missing target dimensions can be linked only from
unambiguous original target records matching its exact firm, issue timestamp,
currency and target value. The output retains all linking record references,
the original missing fields and the match basis. It does not borrow dimensions
from a neighboring firm's record, a similar date, a different value or EPS.
Conflicting simultaneous dimension evidence stays unresolved.

Numeric deltas and percentages are computed from original structured values
using decimal arithmetic. Percent change uses the explicit previous-value
denominator; a zero base yields an undefined percentage. Known conflicting
metric dimensions block numeric comparison. Missing dimensions leave a clearly
conditional reported-value difference, not a verified genuine revision.
Unknown revenue accounting basis does not become GAAP because EPS is GAAP;
retain the literal reported revenue delta with accounting basis UNKNOWN.
Known conflicting revenue accounting bases block comparison.

An initiation label, or a recognized raw initiation phrase, is checked against
every earlier recognized same-firm record. Earlier evidence produces
`UNRESOLVED_COVERAGE_CONFLICT`. It must not be silently discarded because it
lacks EPS metadata or covers a different metric. Issuer/analyst/coverage-scope
equivalence still needs review. Conditional arithmetic does not convert that
conflict into a clean revision. No earlier recognized EPS estimate establishes
only an EPS-record gap, not absence of earlier firm coverage.

All earlier candidate records are retained; multiple references to the same
reported change are not independent revisions or a revision count. Original
cutoffs from target-request sources are respected; later events are retained
but not compared. Conflicting original cutoffs fail rather than selecting a
convenient one. No cutoff means no cutoff was supplied, not current research.

Every original `individual_targets` record also receives a chronological
disposition, even without an `events` row. This route retains all earlier
same-firm target-bearing candidates and their exact source pointers, dates,
issuer, analyst identity, currency, price basis and literal horizon labels.
Different horizon strings remain different: no month/week conversion, alias or
calendar-duration equivalence is inferred. Missing dimensions leave conditional
reported differences with explicit unknowns; known mismatches block arithmetic.
Matching literal dimensions permit a reported target change, not verification
of a genuine independent revision. Other-firm records are never joined.

Same-time target observations are retained separately rather than ordered into
revisions. Known issuer/analyst differences define distinct observations;
unresolved identity is not filled from a neighbor. Conflicting same-time values
or dimensions within the candidate scope suppress numeric comparison. Exact
literal matches and event mirrors retain their separate source references and
never count as independent revisions. Future-cutoff and missing-target records
receive explicit dispositions instead of disappearing. These dispositions are
part of the actual complete Markdown/JSON answer and native replay.

The complete answer combines native comparisons and original-record bindings
with each literal request topic and the whole source inventory. Verification
regenerates the analysis from retained originals and checks both delivered
files. Keep artifact status/link-only cover notes. Review unresolved meanings
and full-request coverage separately; native arithmetic, literal matching and
declared self-review do not certify source truth, semantic completeness or
investment correctness. Preserve first answers and negative findings unchanged.
