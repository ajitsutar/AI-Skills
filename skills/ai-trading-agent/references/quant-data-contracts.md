# Strategy-specific data readiness and revision-aware refresh

These additive offline operations assess supplied evidence. They do not download
data, grant redistribution rights, certify a historical universe, authorize an
order or create a broker approval step. Existing storage and PIT APIs remain
unchanged. Start with the small fictional examples in `examples/quant-data/`.

## Actual strategy requirements, rather than a generic completion flag

`research_readiness.assess(document)` expands the requested strategy into a grid
of decision, security, session, field and purpose. Every needed observation stays
visible as `observed`, `reference`, `modeled`, `unavailable` or `outside_lifetime`.
The result includes failure reasons, counts, source IDs and an input hash.

Required top-level fields:

- `schema_version: 1`, `strategy_id`, `universe_mode` (`current_roster` or
  `historical_membership`), ordered unique exchange `sessions`.
- `sources`: retained structured source records described below;
  `scope_evidence_ids`: the supplied evidence for the calendar/universe scope.
- `securities`: `security_id`, `identity_status` (`source_bound` or `unknown`),
  `evidence_ids`, `listing_intervals`, `membership_intervals`. Each interval has
  inclusive `start_inclusive` and exclusive `end_exclusive`, or null end. A null
  interval list means unknown bounds; an empty list is a declared empty set.
  These interval declarations require substantive evidence review; this helper
  does not infer them or authenticate their supporting sources.
- `requirements`: unique `id`, `field`, `purpose` (`signal`, `valuation`,
  `execution`), security `scope` (`eligible`, `held`, `eligible_or_held`),
  `lookback_sessions`, `unit`, `currency`, and `numeric_domain` (`finite`,
  `positive`, `nonnegative`). Lookback counts include the anchor session; a
  return-volatility requirement of252 daily returns therefore uses252 return
  observations. Obtaining those returns requires a separately audited253 closes.
- `decisions`: unique `id`, `decision_at`, `valuation_at`, `execution_at`,
  `signal_session`, `execution_session`, `held_security_ids`. Eligible securities
  are determined at the signal session. Execution must occur strictly after the
  decision; the user must specify the intended execution convention and actual
  exchange calendar. This helper does not invent session open/close times.
- `observations`: `security_id`, `session`, `field`, `value`, `status`,
  `available_at`, `unit`, `currency`, `source_id`, `source_record_pointer`; optional
  boolean `executable`. Except for unavailable records, the pointed source object
  must contain exactly matching values for every metadata field used. If
  `executable` is supplied, its source annotation must match too. A reviewed
  normalized extraction may provide those annotations; they remain source-review
  claims, not proof of actual market fills. Unknown availability remains null.
- `valuation_policy`: explicit booleans `allow_reference`, `allow_modeled`.

Signal observations must be available by `decision_at`, valuations by
`valuation_at`, and execution observations by `execution_at`. Future or unknown
availability never silently qualifies. Reference and modeled values can qualify
only for a selected valuation scenario, never as signals or fill prices. No close
is substituted for a missing open. Held positions remain in valuation requirements
after index exit; unlisted holdings require corporate-event accounting. A recent
IPO's absent lookback is outside its lifetime but is still insufficient strategy
history, rather than a silently shortened lookback.

Statuses are `DECLARED_STRICT_GRID_COMPLETE`, `DECLARED_SCENARIO_GRID_COMPLETE`,
`RESEARCH_GAPS_REMAIN`, or `NO_REQUIREMENTS_IN_DECLARED_SCOPE`. Even a strict grid
result does **not** certify exhaustive historical membership, source authenticity,
correct corporate actions or a complete strategy implementation. A current-roster
run remains survivor-conditioned. Numeric gap closure by retrospective estimates
does not upgrade strict observed coverage.

The operation bounds each call at two million requirement cells. Split a long
universe-wide campaign by decision dates, retain each input/result hash and combine
counts without changing the requested scope. Do not shorten lookbacks or drop
securities to fit the bound. Source archives stay outside the skill package.

## Source-bound security episodes and historical feature revisions

`security_master.snapshot(document)` resolves identities and episodes from actual
JSON pointers into supplied source bodies. Each source has `id`, `uri`,
`source_role` (`native_json` or `reviewed_extraction`), `retrieved_at`, `body`, and
`body_sha256`, computed by canonical JSON with sorted keys, compact separators,
UTF-8 and nonfinite values forbidden. The body hash checks the supplied bytes'
representation; it cannot authenticate their publisher. A native HTML/PDF source
needs an explicitly labeled reviewed extraction and retained original provenance;
do not label a generated extraction `native_json`.

The document also has `schema_version: 1`, `as_of` (aware timestamp), `on` (valid
date no later than the as-of UTC date), `entities`, and `episodes`.

- An entity has an internal persistent `security_id`, `source_id`, and `bindings`
  for `issuer_id`, `share_class_id`, `instrument_type`, `currency`. Each binding
  is a JSON pointer. CIK alone is not a share-class identifier. Distinct entities
  cannot reuse the same issuer/share-class pair in this narrow master.
- An episode has `security_id`, stable `episode_id`, `source_id`, and bindings for
  `issuer_id`, `share_class_id` (must match the bound entity),
  `kind` (`listing`, `symbol`, `membership`), `value`, `start_inclusive`,
  `end_exclusive`, `announced_at`, `available_at`, `revision_id`.
- Revisions of an episode must retain security/kind/value identity. Equal known
  times and duplicate revisions are rejected. The latest available revision at
  the cutoff is selected before effective-date filtering. Later removal or
  correction knowledge cannot rewrite an earlier as-of snapshot.

Active listing/symbol ambiguity and simultaneous ticker reuse are rejected; a
time-separated reused ticker needs different permanent securities. Multiple
index memberships are permitted. Absence of an active episode is not proof that
the issuer was never listed or included. The narrow schema does not model
simultaneous multiple listings of one security; retain separate reviewed listing
identities or report that ambiguity rather than guessing.

`security_master.adapt_records(document)` maps source pointers to all nine fields
of the existing PIT record: `instrument_id`, `asset_class`, `currency`, `field`,
`event_at`, `available_at`, `value`, `unit`, `revision_id`. Supply `dataset_id`,
`as_of`, `sources` and `records` containing `source_id` and those `bindings`.
The result retains the mapped dataset, source pointers and existing PIT snapshot.
Optional `security_contract` supplies a complete raw master contract at the same
as-of instant; all feature instrument IDs must match its source-bound identities.
Without it, identity linkage is explicitly `NOT_CHECKED`.

Event time and availability are distinct. Neither fiscal period-end nor retrieval
time replaces missing publication/availability. Unit/currency changes across
revisions are rejected by the existing PIT operation. Publication-dated historical
analyst, sentiment and financial data still require real source archives.

## Optional safe price reconciliation

`price_refresh.reconcile(document)` accepts `schema_version: 1`, `mode` (`full` or
`incremental`), explicit boolean `partial_fetch_opt_in`, `current_scope` (`full`
or `tail`), `decision_at`, `acquired_at`, `expected_sessions`, `previous`,
`current`, optional `sources`, `prefix_proof`, and `derived_artifacts`.

Both price snapshots contain `contract`, `rows`, `rows_sha256`, and `revision`.
Contract fields are `provider`, `security_id`, `share_class_id`, `currency`,
`adjustment`, `schema_version: 1`, `parser_version`, `fields`, and matching
per-field `units`. Rows are exactly `session`, `values`, `status`; supported
fields are open/high/low/close/adjusted_close/volume/dividend/split_factor.
Unknown values stay null, zero volume stays zero, and observed/reference/modeled
status survives. No missing field is fabricated. A successor cannot replace a
predecessor security even under a full refresh.

A full current representation is reconciled directly against the prior vintage.
Changed, added and removed dates identify affected declared dependencies. An
adjustment/parser/unit contract change invalidates the entire old/new date union.
The operation retains original hashes and produces a new result without changing
input bytes. This route makes no network-saving claim.

A tail requires explicit incremental opt-in, an identical representation contract,
unchanged overlap, a complete prior prefix and a complete resulting session grid.
It additionally requires a **current native provider prefix manifest** with bound
fields: provider, security_id, contract_sha256, prefix_start, prefix_end,
prefix_rows_sha256, hash_algorithm=`canonical-json-sha256-v1`, current revision,
and checked_at. `prefix_proof` contains its source_id and exact bindings. The
check and source retrieval must lie inside the current acquisition window.
This is an adapter contract, not a claim that Yahoo or another provider publishes
this manifest. If the actual provider cannot establish unchanged normalized
prefix bytes under that exact contract, use full acquisition. Do not fabricate a
manifest from the old local file, TTL or an assertion that no split occurred.

Missing/stale/mismatched proof, changed overlap, representation changes and missing
sessions return `FULL_FETCH_REQUIRED` with no merged rows. Invalid/corrupt inputs
raise errors. Successful cases return `RECONCILED_FULL` or
`RECONCILED_INCREMENTAL`, actual reuse status and new content hash. Dependency
records are `id`, inclusive `source_start`, inclusive `source_end`; affected
artifacts are invalidated, never rewritten. Dependencies must cover the full
source window used by indicators/models, not just their output date.

This helper does not acquire or authenticate provider revision metadata. Until a
provider adapter with that contract is validated, it is a conservative fallback
mechanism and reconciliation tool, not a promise of faster Yahoo downloads.
The existing public collector still defaults to full history acquisition.

## Examples and checks

```text
python scripts/research_readiness.py examples/quant-data/readiness.json
python scripts/security_master.py examples/quant-data/security-master.json
python scripts/security_master.py examples/quant-data/features.json
python scripts/price_refresh.py examples/quant-data/price-refresh.json
python -m unittest discover -s tests -p test_quant_data_contracts.py -v
```

Every example is fictional. The tests cover future/subsecond publication clocks,
later restatements, explicit valuation scenarios, missing opens, held positions
after membership exit, recent-IPO lookbacks, source/metadata corruption, null
volume, overlap corrections, source-contract changes, missing native prefix
proof and immutable results. They validate operations, not the historical S&P900
dataset or a profitable strategy.
