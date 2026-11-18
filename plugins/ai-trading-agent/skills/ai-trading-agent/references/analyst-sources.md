# Analyst research from original source bytes

`analyst_sources.analyze(request, manifest_path, expected_manifest_sha256,
source_root=None)` performs extraction, corpus inventory, chronology, eligible
cohort calculation and deterministic report generation together. It does not
accept manually constructed target rows. The manifest pin must come from outside
the analysis; it verifies retained file identity, not publisher authenticity.

When the pinned corpus includes a canonical original analyst request, bind the
whole JSON root instead of transcribing its dimensions:

```json
{
  "original_request_ref": {"source_id": "request-source", "pointer": ""},
  "extraction_profile": {
    "formats": ["json_records", "labelled_records", "labelled_sentences"]
  }
}
```

`source_id` is an ID in the externally pinned manifest. This form accepts no
literal cohort, timestamp or age overrides. A canonical root contains `issuer`,
`currency`, `price_basis`, `target_horizon`, `as_of` and `individual_targets`.
Optional fields are `provider_consensus`, `analyst_track_records`, `quote`,
`source_discovery`, `max_target_age_days` and `max_quote_age_hours`. Collections
must be arrays; quote may be an object or null. Unsupported root policy fields
or malformed contract fields fail explicitly. Nested request selection is not
supported; no parent/sibling fields or filenames identify request authority.

The producer derives exact cohort strings and cutoff, plus the supplied positive
age constraints. It preserves opaque share-basis labels without alias conversion.
Absent age limits use the existing documented defaults, 90 days and 96 hours,
labelled as defaults rather than source values. Decimal ages retain their source
representation; values that cannot be converted without precision loss reject.
Target age controls eligibility. Quote age is retained but unused because this
producer does not perform quote analytics. Quote, performance records and source
discovery remain original retained members, explicitly unconsumed here.

The legacy literal form remains available for record-only/text corpora:

```json
{
  "as_of": "2026-04-20T12:00:00Z",
  "cohort": {
    "issuer": "SYN",
    "currency": "USD",
    "price_basis": "common_share_unadjusted",
    "target_horizon": "forward_12_months"
  },
  "extraction_profile": {
    "formats": ["json_records", "labelled_records", "labelled_sentences"]
  }
}
```

It may additionally supply positive `max_target_age_days` and
`max_quote_age_hours`. Every invocation checks JSON source roots for canonical
request contracts, including legacy invocations. With one original contract,
literal cohort/cutoff/policy conflicts fail as
`ORIGINAL_ANALYST_REQUEST_FILTER_MISMATCH`; matching literals use original policy.
Multiple originals require an explicit root reference, even if their values
match. Malformed contract-shaped roots cannot fall back to declared-only mode.
Without an original contract the result is `DECLARED_FILTER_ONLY`.

The cohort is a filter. Its values never fill missing fields in original records.
No caller-supplied regexes, literal target overrides, firm aliases, metadata
defaults, filename lists or manual relevance dismissals are accepted.

Supported bounded formats:

- `json_records`: nested JSON objects with a literal `target` scalar and optional
  canonical keys `firm_id`, `analyst_id`, `issuer`, `currency`, `issued_at`,
  `published_at`, `observed_at`, `price_basis`, `target_horizon`, `access`, `url`.
  The three source metadata fields may also come from that record's own immediate
  `source` object, with direct/nested conflicts rejected. Parent/sibling metadata
  is not inherited. Canonical provider-pool records are also supported under the
  [bounded provider contract](analyst-research.md#delivered-dispersion-and-provider-context).
- `labelled_records`: one record per line, canonical `key: value` fields separated
  by semicolons. For example `firm_id: Quill; target: 63.5`. Duplicate/unknown keys
  make the candidate unresolved. Missing metadata stays missing.
- `labelled_sentences`: explicit sentences of the form
  `Firm Quill, analyst Ava, issued 2026-04-02T10:00:00Z: SYN target USD 63.5 per common share; horizon forward_12_months; access FULL_REPORT. No split adjustment.`
  The bounded revision form `Quill initiated new coverage April 9: FY2030 adjusted EPS USD 3.70; target USD 71.` retains the firm, target and currency, but does not
  invent a year, issue timestamp, horizon, issuer or report access.

These grammars are not general natural-language understanding. HTML/Markdown
tables, other narratives, noncanonical provider consensus pools, ambiguous labels, binary
sources and target-like JSON outside supported records remain unresolved.
Every manifest source is inspected regardless of filename. Unsupported target
candidates remain attached to original pointers or exact character spans. A
configured scan does not establish semantic completeness or source absence.

The result contains `records` with fields and original-role bindings,
`source_inventory`, `coverage`, `observed_latest`, `eligible_cohort`,
`request_binding` and `report`. Request binding records the original source hash,
root/member pointers, effective filters, field origins, explicit defaults and
unconsumed members. Decimal source values are recorded as strings with
`source_value_type: decimal`; effective age values use the helper's numeric type.
Binding is rederived by native source/report/response replay. It proves exact
field provenance, not semantic understanding of which original the user intended
or complete analysis of every original member.
`observed_latest` describes only parseable issue chronology for the requested
issuer. Unknown issuers/dates remain unresolved; other issuers and known future
issues or availability times are explicitly excluded. Selected records retain
currency, share basis, horizon and original references; mixed dimensions are not
aggregated. Unknown-date revisions can supersede its rows; conflicts are retained. `eligible_cohort`
delegates fully attributed rows to the existing analyst evidence helper and
retains both prefilter and helper exclusions. An older eligible row is not
thereby the latest observed issue. Twelve-month and 52-week horizons remain
distinct. Publication, observation and issue times are separate source fields;
none is synthesized from another clock.

Nonempty cohort results include explicit range width, IQR and the linear quartile
method; empty cohorts remain unavailable. Separately bound provider pools and
their population-specific upstream declarations appear in the same generated
report and canonical response. They never enter the individual-target arithmetic.

The report is generated in the same invocation and carries its UTF-8 SHA256.
All identifiers and output fields are deterministic. Replay the producer using
the same original pinned sources and compare the complete result before auditing
saved report bytes. A report hash alone does not verify source semantics or added
free prose. `whole_report_semantic_pass` remains false. The wrapper must retain
unknowns, rejected records and original coverage; do not turn an empty eligible
cohort into an invented complete consensus. There is no network, broker or
publication operation.

Provider statistics use the same precision-checked numeric conversion as individual targets. Supported fractional values retain their original field pointers and numeric bindings; JSON spellings such as `107` and `107.0` have equivalent eligibility. Unsupported precision remains an explicit source gap. Provider counts remain positive integers.

Recognized original-request dimensions, age policies and supported collections do not themselves create unsupported-target warnings. Their children are still scanned: genuinely unknown target objects remain unresolved. Recognizing these roles does not establish semantic completeness or source absence.
