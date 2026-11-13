# Analyst research from original source bytes

`analyst_sources.analyze(request, manifest_path, expected_manifest_sha256,
source_root=None)` performs extraction, corpus inventory, chronology, eligible
cohort calculation and deterministic report generation together. It does not
accept manually constructed target rows. The manifest pin must come from outside
the analysis; it verifies retained file identity, not publisher authenticity.

The request has exactly three keys:

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

The cohort is a filter. Its values never fill missing fields in original records.
No caller-supplied regexes, literal target overrides, firm aliases, metadata
defaults, filename lists or manual relevance dismissals are accepted.

Supported bounded formats:

- `json_records`: nested JSON objects with a literal `target` scalar and optional
  canonical keys `firm_id`, `analyst_id`, `issuer`, `currency`, `issued_at`,
  `published_at`, `observed_at`, `price_basis`, `target_horizon`, `access`, `url`.
  Only fields in the same object bind; parent/sibling metadata is not inherited.
- `labelled_records`: one record per line, canonical `key: value` fields separated
  by semicolons. For example `firm_id: Quill; target: 63.5`. Duplicate/unknown keys
  make the candidate unresolved. Missing metadata stays missing.
- `labelled_sentences`: explicit sentences of the form
  `Firm Quill, analyst Ava, issued 2026-04-02T10:00:00Z: SYN target USD 63.5 per common share; horizon forward_12_months; access FULL_REPORT. No split adjustment.`
  The bounded revision form `Quill initiated new coverage April 9: FY2030 adjusted EPS USD 3.70; target USD 71.` retains the firm, target and currency, but does not
  invent a year, issue timestamp, horizon, issuer or report access.

These grammars are not general natural-language understanding. HTML/Markdown
tables, other narratives, provider consensus pools, ambiguous labels, binary
sources and target-like JSON outside supported records remain unresolved.
Every manifest source is inspected regardless of filename. Unsupported target
candidates remain attached to original pointers or exact character spans. A
configured scan does not establish semantic completeness or source absence.

The result contains `records` with fields and original-role bindings,
`source_inventory`, `coverage`, `observed_latest`, `eligible_cohort` and `report`.
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

The report is generated in the same invocation and carries its UTF-8 SHA256.
All identifiers and output fields are deterministic. Replay the producer using
the same original pinned sources and compare the complete result before auditing
saved report bytes. A report hash alone does not verify source semantics or added
free prose. `whole_report_semantic_pass` remains false. The wrapper must retain
unknowns, rejected records and original coverage; do not turn an empty eligible
cohort into an invented complete consensus. There is no network, broker or
publication operation.
