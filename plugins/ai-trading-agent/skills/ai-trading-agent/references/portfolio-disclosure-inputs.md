# Public disclosure inputs and on-demand refresh

The host obtains and reviews public sources; `scripts/portfolio_disclosures.py`
normalizes retained input. It does not fetch websites, authenticate a source,
reconstruct private accounts, schedule a monitor or submit orders. Run only when
requested. The source catalog identifies public discovery locations; an account-only
Autopilot strategy is not made reproducible by a similarly named public filing.

## Common record contract

`normalize(document)` accepts `kind`, `as_of` and `subject_id`. Timestamps carry
explicit timezone offsets. The result contains `records`, `excluded_rows`,
`warnings`, `input_sha256` and `status` (`normalized`, `partial` or `unavailable`).
These are parsing/completeness results, not source-authentication certificates.

Each source record provides `event_id`, integer `revision`, boolean `withdrawn`,
`source_ref`, `event_at`, `published_at` and `available_at`, with
`event_at <= published_at <= available_at <= as_of` for usable records. Future
disclosures are excluded. Use immutable accession/document plus row identities
for events and explicit amendment lineage for revisions. Do not assign a new event
ID just because the same filing was downloaded again. A higher revision is an
explicit correction; a withdrawn record never means resurrect its old version.

`event_at` is the transaction/recommendation time or snapshot's period end.
`published_at` is public release time. `available_at` is the earliest time the
retained evidence can support using this record; retain the first verified capture
if historical availability is unproven. Optional `retrieved_at` describes this
fetch and must not precede `available_at`. Refresh time must not be substituted for
the economic event date to make an old signal look recent. Retain original source
bytes and capture metadata privately outside the installed package.

## SEC 13F information tables

`kind: sec_13f` takes `source`, `information_table_xml` and `security_map`.
The `source` object includes the common record fields plus:

- `form`: `13F-HR`, `13F-HR/A`, `13F-NT` or `13F-NT/A`.
- `amendment_type`: `none`, `restatement` or `new_holdings`, consistent with the form.
- `currency: USD`, explicit `value_unit: USD` or `USD_thousands`.
- `table_sha256`: SHA-256 of the exact UTF-8 XML string, including whitespace.
- `expected_table_entry_count` and `expected_table_value` from the cover-page
  summary, using the declared source value unit; no unit guessing from year or size.
- `reported_table_complete: true` only after the entire reported table was captured;
  `source_reviewed: true` only after the host checked the identified source.
- Optional `included_managers`, preserving the filing's attribution rather than
  pretending all positions are one celebrity's personal holdings.

Each security-map entry supplies `cusip`, stable `security_id`, `asset_type`,
`valid_from`, optional exclusive `valid_to`, `available_at` and `source_ref`.
Identity mappings must apply at the holdings date and be available by `as_of`.
The normalized record's availability is delayed to the latest mapping it used.
Never infer a ticker from a familiar issuer name. Multiple active mappings fail.

Only mapped `common_stock` rows with share (`SH`) quantities and no `putCall`
field enter the eligible basket. Options and principal-amount rows remain excluded
with their reported values; option underlying values are not premiums. Unmapped
share rows or a cover/table mismatch make `complete_reported_basket` false, so
the target helper preserves the previous allocation instead of silently overweighting
the successfully mapped subset. A complete reported common-stock basket still
omits cash, short positions, other asset types and potentially confidential holdings;
it is never the manager's complete portfolio NAV.

A 13F notice yields no snapshot: follow its identified reporting manager. An
additional-holdings amendment requires explicit reconciliation against the base
filing outside this helper; it is not a complete replacement. A declared full
restatement may replace the linked snapshot, preserving revision identity.
Empty/unreadable tables are errors, not liquidation signals.

## Politician transactions and public recommendations

`kind: public_transactions` takes `events`. Each event includes the common fields,
`security_id`, `asset_type`, `identity_reviewed`, `source_reviewed`, `owner`,
`action` (`BUY`, `SELL`, `PARTIAL_SELL`), and optional `sale_scope`
(`full`, `partial`, `unknown`). `PARTIAL_SELL` becomes `SELL` with partial scope.
Unknown actions, such as an exchange requiring interpretation, are excluded.
Capture owner attribution (self/spouse/dependent) and the original disclosure row.

Optional `amount_range` contains `lower`, nullable open-ended `upper`, and
`currency`. Ranges remain ranges: `exact_quantity` and `actual_portfolio_weight`
remain null. Neither the midpoint nor a maximum disclosed amount is a known
position size. Options, private interests and unresolved identities do not qualify
as common-stock signals. Complete snapshot holdings cannot be inferred from a
sequence of incomplete transaction disclosures.

`kind: public_recommendations` additionally requires `speaker_verified: true`,
`recommendation_verified: true` and `source_context: original_recommendation` to
qualify an event. Keep `speaker` and a known `horizon` (otherwise `unspecified`).
These are host review declarations. A headline, quote of someone else's opinion,
sarcasm, an educational example or a mere mention is not a qualifying signal.
Direction is the speaker's original call; the follower engine applies the selected
inverse rule later. It never means that the speaker owns that stock.

Use normalized `records` in the matching snapshot/events/inverse sleeve described
in [follower calculations](portfolio-follower-calculations.md). Inspect exclusions
and source freshness before setting a sleeve's source status. Do not turn a parser
status into independently verified source provenance.

## Incremental checkpointing without a schedule

`changes({current: normalization_input, previous: checkpoint_or_null})` is pure.
It returns normalization results, new/updated event IDs and a proposed checkpoint.
The initial successful baseline suppresses historical mass alerts. If an initial
fetch was unavailable, the first successful fetch still establishes the baseline.
Omitted records are retained; absence is never an implicit withdrawal.

Semantic comparison retains event/publication clocks but excludes fetch/availability
timestamps. A later retrieval of unchanged source content is not a correction.
The checkpoint preserves the first observed availability for each saved revision;
it does not retroactively move first knowledge earlier. Contradictory same-revision
content stays in `unresolved_conflicts` and cannot overwrite the last known record.
A valid higher revision resolves it. Keep the full result and raw captures as
evidence; checkpoint hashes alone are not source archives.

Checkpoint `as_of` is the last attempt time. `last_successful_as_of` advances only
on a normalized, conflict-free result; `last_attempt_status` and unresolved conflicts
remain explicit. None of these fields proves a source is current or complete today.
Snapshot period ends and event ages still govern strategy freshness.

The explicit CLI can commit a checkpoint with an exclusive local lock and atomic
replace. It creates no recurring task and never breaks an existing lock:

```console
python scripts/portfolio_disclosures.py examples/portfolio-disclosures.json
python scripts/portfolio_disclosures.py retained-input.json --checkpoint PRIVATE_RESEARCH_DIR/follower-checkpoint.json
```

The checkpoint parent directory must already exist. Choose a private research
directory outside the installed skill and repository. If an interrupted run left a
lock, reconcile that run before removing the lock. The pure workbench path does
not invoke this writer. Concurrent runs on the same checkpoint fail fast.
