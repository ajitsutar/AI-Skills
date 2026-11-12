# Bind news clocks, range calculations and report claims

Use `scripts/news_evidence.py` when adapting retained JSON/text sources whose clocks
or metric basis are incomplete, when comparing revisions sharing a publication
date, or when checking that a report attributes only emitted helper fields.
This adapter complements `news_analysis.py`; it performs no acquisition, source
authentication, free-text semantic certification or trading operation.

## Source-bound comparison

Run `python -B scripts/news_evidence.py compare request.json source-root result.json`.
The result is created exclusively; select a fresh path for every run. Keep the
original sources and failed attempts unchanged. Every source reference contains
its original relative `path` and SHA256. A modified mapping cannot replace a
source timestamp or numeric field: any supplied `value` must equal the extracted
source value. Relative paths must remain inside the source root without links.

The request has `as_of`, `previous` and `current`. Each record has an `id`, `source`,
`clocks` and `fields`. Fields are `issuer`, `metric`, `period`, `currency`, `unit`,
`accounting_basis`, `low`, `high`. Ranges must be source-bound finite numbers.
For a structured source containing the corresponding fields, a record looks like:

```json
{
  "id": "previous",
  "source": {"path": "previous.json", "sha256": "ACTUAL_SOURCE_SHA256"},
  "clocks": {
    "publication": {"kind": "source", "pointer": "/published_at"},
    "observation": {"kind": "unknown"}
  },
  "fields": {
    "issuer": {"kind": "source", "pointer": "/issuer"},
    "metric": {"kind": "source", "pointer": "/metric"},
    "period": {"kind": "source", "pointer": "/period"},
    "currency": {"kind": "source", "pointer": "/currency"},
    "unit": {"kind": "source", "pointer": "/unit"},
    "low": {"kind": "source", "pointer": "/low"},
    "high": {"kind": "source", "pointer": "/high"},
    "accounting_basis": {"kind": "unknown"}
  }
}
```

Bindings use exact RFC6901 JSON pointers. For a text field, add `span: [start, end]`
to select a half-open Unicode-character span from the original decoded string.
Without a pointer the span addresses the original UTF-8 text file. Preserve original
newlines when calculating offsets. Spans are literal extraction, not semantic
proof that a selected value belongs to the intended financial metric.
For an archive, set `source.record_pointer` (for example `/documents/0`) to bind
one original object before resolving every field/clock pointer relative to that
object. This prevents a local pointer from reaching a sibling archive record.

Publication clock pointers must end in `published_at` or `publication_time`;
observation pointers must end in `observed_at`, `first_observed_at` or `first_seen_at`.
Text clocks can use `kind: source, label: Published` or `First observed` respectively;
the label must occur exactly once at the beginning of a source line. Missing clocks
remain `kind: unknown`. An explicitly requested fictional convention may be retained
as `kind: assumption, value: <timestamp>, reason: <explanation>`; it never becomes a
source observation or publication. Do not change a dateline to the first-observation
time to make two releases ordered.

For declared dimension mappings use `kind: declared, value: ..., reason: ...`.
Unknown accounting basis remains `kind: unknown`. A structured source basis must
come from `accounting_basis` in the same JSON object whose `metric` equals this
record's metric. For prose use `kind: source_phrase`, `value: <basis>` and a
pointer/span selecting the source phrase. The limited recognizer accepts a basis
immediately before the metric (for example `IFRS revenue`) or a numeric metric
range ending `on a IFRS basis`. It does not infer revenue's basis from a nearby
margin statement. Unrecognized prose stays declared/unknown for human review;
do not edit the source or excerpt to satisfy the recognizer.
Original surrounding clauses are checked even for a selected span: `non-GAAP`
cannot supply a `GAAP` association, and negated/contrastive basis clauses remain
unresolved. Exact `non-GAAP` can itself be a source basis. This conservative grammar
may reject valid but complex phrasing; retain unknown/declared basis instead of
treating rejection as proof of a different basis.

Source decimal tokens are retained as exact decimal strings rather than binary
floats. Range arithmetic supports at most 24 coefficient digits and decimal
exponents from -24 through +24; values outside those bounds fail explicitly.
Calculations use a local 80-digit Decimal context, independent of caller settings.
Recurring percentages are rounded to that precision. These bounds avoid silent
loss of a small endpoint change beside a large value.

The adapter always returns the extracted fields, clock roles and limitations.
`SOURCE_BOUND_DISCLOSURE_CHANGE` requires supported comparable fields, source
clocks and strictly later publication. It remains byte/field binding, not verified
source authenticity or economic meaning. `ARITHMETIC_ONLY` retains descriptive
range deltas when clocks/basis or dimensions require review, or when publication
is unchanged/earlier; it does not assert a later guidance disclosure. The
`publication_order` remains separate from range direction. A late observation of
an old-dated revision cannot become a new disclosure. Known future source clocks
produce `EXCLUDED_AT_CUTOFF` with no as-of arithmetic. Conflicting dimensions or
known bases produce `NOT_COMPARABLE`. Source binding or role violations raise an
error rather than generating a fallback from corrupt evidence.

## Audit claims against the actual saved result

Run `python -B scripts/news_evidence.py audit claims.json output-root audit.json`.
Bind the exact full result file, not a manually reconstructed result or a compact
stdout view that omits rows. Example input:

```json
{
  "output": {"path": "triage-result.json", "sha256": "ACTUAL_OUTPUT_SHA256"},
  "claims": [
    {"id": "event-label", "pointer": "/records/0/review_events",
     "relation": "contains", "value": "GUIDANCE_REVIEW"},
    {"id": "tone", "pointer": "/records/0/language/label", "value": "UNSCORED"}
  ]
}
```

Each claim uses exact `equals` (default) or list-membership `contains`.
Supply at least one claim with a distinct nonempty `id`; an empty check is not a pass.
`CLAIM_MISMATCH` preserves the claimed and actual values, including absent
pointers. Decimal result values are rendered as exact strings with their original
JSON type reported; equality checks compare decimal numbers without float conversion.
A label present in prose but absent from `review_events` is interpretation,
not an emitted helper result. Build tool-attributed report facts from supported
claims and retain interpretation separately. This checker does not validate
arbitrary prose or establish that the saved output was actually executed; retain
the original command, source snapshot, output and exit evidence alongside it.
