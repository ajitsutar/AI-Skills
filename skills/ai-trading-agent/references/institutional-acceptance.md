# Institutional deployment evidence

Use `scripts/institutional_acceptance.py` when assessing a particular research,
paper or live deployment from retained evidence. It replays the existing platform,
source-study, rights and review-packet assessors, joins their scope identities and
reports missing evidence. It makes no network, model, host or broker calls. Ordinary
investment research does not require running this workflow.

```text
python scripts/institutional_acceptance.py acceptance.json --evidence-root /private/evidence --output acceptance-result.json
```

The output is created exclusively; existing output and input files are preserved.
Exit 0 means the declared scope's evidence catalog is complete. Exit 2 means gaps
or invalid input. Inspect every component's status and the value criterion: a
complete catalog can document a negative value result. Neither exit code nor
`DECLARED_SCOPE_EVIDENCE_COMPLETE` certifies institutional readiness, investment
effectiveness, legal compliance or permission to execute.

## Bind one deployment

The input has exactly `schema_version: 1`, an offset-aware `as_of`, `scope` and
`components`. Each component has `kind` and `artifact: {path, sha256}`; the digest
is the retained file's raw SHA-256. Paths use forward slashes relative to the
explicit evidence root. The root and path must not traverse symbolic links or
junctions. Inputs are bounded to 16 MiB, JSON nesting to 64, and duplicate keys
and nonfinite numbers are refused. Keep credentials and contact configuration
outside this root. Named exclusions and sensitive-key checks are input hygiene,
not a general secret scanner. Retained opaque control/output files remain private.

The exact scope fields are:

| Fields | Meaning |
|---|---|
| `id`, `description`, `host_id` | Explicit deployment and actual host identity |
| `mode`, `asset_classes` | One platform mode and explicit unique supported asset classes |
| `package_sha256`, `runtime_sha256` | The package/runtime identities used by platform evidence |
| `intended_use` | `personal_research`, `commercial_internal` or `redistribution` |
| `claimed_benefits` | Exactly one of `automated_quality`, `human_productivity`, `alpha` |
| `data_contract_sha256` | Canonical digest of the source-study input's `study_request` |
| `universe_mode`, `data_policy` | `historical_membership` or `current_roster`; `strict_observed` or `declared_scenario` |
| `source_rights_map` | Every used source ID mapped to its retained rights-inventory row ID |
| `review_protocol_sha256` | Raw digest of the adopted review protocol inside every sealed packet |
| `value_protocol_sha256` | Canonical digest of the prespecified value protocol |

Canonical digests use sorted-key compact UTF-8 JSON, non-ASCII characters retained
and nonfinite numbers refused (`institutional_acceptance.digest`). Build identities
in this order: data contract; review protocol; scope without the value pin; value
protocol whose `scope_sha256` is the digest of `value_scope_identity(scope)`;
finally set the value pin and bind controls to the digest of the complete scope.
This excludes only the value protocol's own pin from its scope identity.

## Retain original assessor inputs

Research requires `platform`, `data`, `rights`, `review_packet`, `governance`,
`operations` and `value` components. Other modes also require `implementation`.
Supply original native inputs, not copied success labels:

- `platform`: [platform readiness](platform-readiness.md) input with the same host,
  package/runtime, cutoff, assets, mode, scope ID and description.
- `data`: [source strategy readiness](quant-data-contracts.md) input. Study clocks
  and source captures must not be later than acceptance. The selected universe
  mode's strict-observed or declared-policy grid must actually be complete.
  A declared scenario is not observed coverage; current rosters are not historical
  membership. Preserve those qualifications in the decision.
- `rights`: [rights inventory](release-acceptance.md) input with the same cutoff
  and intended use. Every mapped row must retain the actual data source URI.
  Inventory completeness verifies declarations; it grants no data rights.
- `review_packet`: `{packets: [{packet_directory, packet_sha256}]}` for every
  registered case, up to 1,000. The [packet verifier](review-packet.md) checks each
  sealed packet. Protocol pins, registered rosters and unique case identities
  must agree. Packet review times must precede acceptance. The adopted protocol
  JSON also needs `scope_id`, `host_id`, `package_sha256`, `runtime_sha256` and
  `data_contract_sha256` matching the deployment. This prevents unrelated packet
  success from qualifying another host or study.

## Governance, operating evidence and implementation

Each control document has exactly `schema_version: 1`, `scope_sha256`,
`package_sha256`, `runtime_sha256`, `observed_at`, `valid_until`, `owner` and
`checks`. Each check has `id`, `outcome` (`pass`, `fail`, `not_run`), `reviewer`
and a nonempty list of retained `{path, sha256}` evidence files. The assessment
cutoff must be within the control's observed/valid interval. Missing or unrun
checks remain gaps; a reviewer label alone is insufficient without retained bytes.

Governance IDs: `classification`, `approved_model_routes`, `access_separation`,
`retention_and_deletion`, `permitted_data_use`, `confidential_data_negative_test`.
Operating IDs: `named_support_owner`, `source_and_model_change_monitoring`,
`incident_response_drill`, `restart_recovery`, `rollback_drill`,
`deployment_change_review`. Implementation IDs: `cost_and_borrow_basis`,
`liquidity_and_capacity`, `observed_vs_assumed_execution`.

Record actual exercises and their limitations. File integrity does not authenticate
the reviewer or prove the contents true. The deployment must enforce its own access,
retention and model routing controls. This tool supplies no custody, surveillance,
team identity management, incident response service or broker enforcement.

## Compare a prespecified benefit

The value component has `schema_version: 1`, `protocol`, `observations`. The exact
protocol fields are `id`, `scope_sha256`, `review_protocol_sha256`, `registered_at`,
`measurement_kind`, `expected_case_ids`, `evaluation_units`, `criterion`.
`measurement_kind` is `automated_proxy` or `human_reported`. The expected roster
must equal the review protocol's roster; `evaluation_units` maps each case to a
nonempty unique list of fixed review-unit IDs. The criterion has `metric`,
`direction`, `minimum_improvement`. Directions are fixed: `material_errors`,
`total_seconds`, `cost_usd` are lower-is-better; `decision_checks` is higher-is-better.
Quality claims require error/check metrics. Human-productivity claims require a
human-reported time or cost metric. Alpha is always unassessed by this comparison.

Each observation has exactly `id`, `reviewer`, `review_packet_sha256`,
`common_inputs`, `packet_frozen_at`, `baseline`, `assisted`. `common_inputs` is a
file reference to the actual packet common-input inventory; its canonical digest
must equal the verified packet's `common_input_sha256`. The protocol must be
registered by packet review, with review no later than freezing, and both arm
captures strictly after freezing and no later than acceptance.

Each arm has exactly `captured_at`, `common_input_sha256`, `output` (file reference),
`reviewed_unit_ids`, `material_errors`, `decision_checks`, `work_seconds`,
`review_seconds`, `correction_seconds`, `cost_usd`. Error and satisfied-check counts
are counts of distinct reviewed units, at most one occurrence per unit; check
attempts are not satisfied checks. Both arms must cover all fixed units. Unequal
or partial coverage gives no comparable improvement. Missing phase durations or
costs stay null, never zero. The total duration includes all three declared phases.
Numeric metrics are finite/nonnegative with at most 40 digits and bounded decimal
range; arithmetic runs in an isolated decimal context.

Only registered cases enter the arithmetic mean improvement. Unexpected IDs are
retained and excluded; missing cases prevent a complete result. The threshold is
applied only to the full matched roster. Retained outputs and declared reviewer
counts do not authenticate human activity, establish causal time savings, remove
model-training hindsight or demonstrate economic alpha. Report the mean, coverage,
reviewer type, criterion outcome and these limits together.
