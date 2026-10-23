# Enforced research contract and final selection

Preserve the requested ranking route independently of a supplied snapshot's
compatible diagnostic profile. For an unspecified fundamental method, use the
public default and `ranking_alignment`'s `requested_basis: documented_default`;
do not call a strict diagnostic SAME merely because it can replay.
Before the final allocation or fixed-exit recommendation, use the source-bound
context report in [portfolio decision calculations](portfolio-decision-calculations.md).
Carry its known concentration and monetary-volume facts, conditional-scenario
risk, cash comparator terms and missing adverse-thesis/exit-plan evidence into
the answer. These are advisory reporting requirements, never execution gates.

Use this workflow for new ranked fundamental or dated stock-pick requests. It
closes the gap between a reproducible discovery score and discretionary final
tables. Intraday remains a separate registered-signal workflow. Do not reroute an
explicit momentum/other strategy to VQM; disclose when its requested implementation
is unavailable. An unspecified aggressive posture is not permission to invent
beta, analyst-count, price-momentum or earnings-blackout filters.

## Lock the actual mandate

Resolve universe before selecting names using
[the mandatory default rule](../SKILL.md#mandatory-default-stock-universe).
If no applicable user instruction supplies a different scope, lock the entire
U.S. exchange-listed stock universe and retain its membership evidence. Do not
encode an assistant-generated analyst/news finalist list as a user mandate.
An output count limits requested selections, not discovery membership. Record
the actual user instruction for any scope override; later runtime failures do
not silently amend the locked universe.

Before selecting names, save a JSON object with `prompt`, `universe`, `hold`,
`information_cutoff`, `price_date`, `entry_at`, `comparison_at` (or the legacy
`exit_at` comparison-clock name), `standing_preferences`, `selection_mode`,
`allowed_statuses`, and `custom_filters`. Preserve supplied `count`, `capital`,
`risk_posture`, `early_exit_policy`, and `earnings_policy`; do not invent them.

Resolve the analytical comparison clock through horizon_review.py first. Timestamp
fields must include timezones. `count` is optional: omitted or null means no output
quota, and the entire finite research queue must be reviewed for final completion.
A supplied positive count is a requested target, not a guarantee of that many
supported choices. `capital` is optional for `research_intent: ranking` (the default)
and required for `research_intent: allocation`; sizing must not invent a budget.
These inputs do not change the public factor formula.

Omitted `risk_posture` and `early_exit_policy` become `unspecified`, with
`field_provenance` set to `unresolved`. Omitted `earnings_policy` becomes
`allow_with_disclosure` with provenance `documented_default`. An explicit exclusion
remains `exclude_during_hold`. An explicitly null/invalid earnings policy must be
resolved; it is not silently treated as the omission default. Supplied fields use
`user` provenance unless the caller already records a valid provenance value.
Keep unknown intent descriptive; do not turn it into inferred filters or limits.
`standing_preferences` is `ignore` only when requested, otherwise
`explicit_in_this_mandate`: copy applicable user instructions explicitly, never
silently inherit another model's assertions about standing rules.
These settings affect research selection only; the skill imposes no execution controls.
`selection_mode` is `computed_order`; `custom_filters` is `[]` for this shared
profile. `allowed_statuses` is `["Eligible"]`, or `["Eligible", "Speculative"]`
for an explicitly aggressive speculative research comparison. This is not a
claim that Speculative is suitable for a user with a guaranteed-loss constraint.

```text
python scripts/research_handoff.py lock /run/mandate.json /run/contract.json
```

The contract pins implementation hashes and profile. It grants no trading authority.
Changing its rules requires a new contract, not editing an already frozen run.
Schema 2 adds optional intent and explicit horizon metadata. Archived contracts
remain bound to their original implementation and must be replayed with that code.
Verification does not silently migrate schema, hashes or previously accepted
explicit mandate values. Create a new contract for a new run after an upgrade.
Complete packages must pass research_preflight.py, including manifest verification.
SKILL.md alone, stale agent entrypoints, or a version string without files do not
establish the installed implementation. Instructions cannot force a model to use
tools; require execution artifacts and reject unsubstantiated conformance claims.

## A comparison date is not a forced sale

`horizon_mode: comparison` is the default and carries `forced_exit: false` and
`hard_exit_at: null`. Use `flexible_review` for an explicitly flexible thesis-review
horizon, also with no forced exit. Set `fixed_exit` only for an actual user-specified
hard exit; it carries `forced_exit: true` and `hard_exit_at` matching the comparison
date. These are research intent metadata, not an order or automatic sell schedule.

The current adapter still calls the full `fixed_horizon` analytical comparison
review, so primary evidence, scenarios, event coverage and exact timestamps retain
the same requirements. Its `exit_at` is the compatibility name for `comparison_at`;
never copy it into a host sell instruction for a flexible/comparison mandate. If a
flexible request supplies no comparison date, declare a provisional valuation or
review date before running this helper rather than inventing a hard sale date.
Long-term event coverage can use the existing sourced `rolling_review` mode; dates
beyond that window remain unassessed. A bare `decision_mode: long_term` review does
not replace the handoff's exact-horizon evidence contract.

## Check release freshness, not just retrieval time

Keep the original public snapshot unchanged. Build a ledger containing
`contract_sha256`, `acquisition` (`independent_fresh`, `shared_snapshot`, or
`incremental_reuse`) and `rows`. Every checked row has:

- `symbol` and `vendor_row_sha256` from the scorer's field audit.
- `latest_release`: primary `url`, `kind` (`issuer` or `regulator`), relative saved `file` path, source-byte
  `content_sha256`, timezone-bearing `published_at`, and actual `period_end`.
- `release_index`: primary URL/kind/relative file/content hash of the listing searched for newer
  earnings releases and amendments. Retrieve and preserve actual source bytes.
- `checked_at`, `reviewed_period_end`, `amendments_checked: true`, and
  `unresolved_restatements: false` only when those reviews were performed.
- `earnings_during_hold`: a sourced boolean when advancing a final comparison.
- `period_bridge` only when a reviewed fiscal-week versus vendor-month-end label
  differs by at most seven days; this is not a waiver for a newer quarter.

For later retrieval of evidence that was publicly available at the frozen cutoff,
retain the actual `checked_at`, set `information_as_of` to the cutoff, and supply
`point_in_time_evidence` identifying the dated archived release/filing and why the
content represents that date. Later amendments cannot be imported retrospectively.
Never backdate the retrieval time to pass a gate.

The helper requires actual nonempty source files for both the release and release
index, verifies their byte hashes inside `--source-root`, and blocks traversal or
missing/mismatched files. Hash strings without files leave freshness UNKNOWN.
This proves byte binding, not source authenticity: invented files, fabricated URLs
and unsupported assertions remain invalid evidence. The helper also blocks unknown,
stale, future, mismatched or restated financial evidence.
A vendor row can be freshly downloaded yet omit a release published days earlier.
Never call missing dates "clear" or remove the stale issuer as an inferior stock.
Use other appropriate sources immediately when a provider lags; Yahoo is neither
mandatory nor authoritative. SEC filings and issuer releases take precedence for
reported financials; accessible Morningstar and other vendors can supply or
cross-check standardized fields, estimates, prices and events. Respect access
permissions and distinguish reported GAAP from adjusted numbers and forecasts.
Preserve the gap and use a separately sourced strict normalization run, or the
audited correction workflow below. Do not silently inject numbers into a
vendor-only profile. Known stale data anywhere
in the scored universe blocks a final selection until corrected and reranked: a
lower-ranked issuer might move above the review frontier.

Checking only finalists cannot certify the freshness of the entire universe.
Report unchecked coverage. Primary index review, correct period mapping and source
authenticity remain research tasks; a self-declared hash is not proof of them.

## Correct a stale input using other sources

`scripts/research_source_overlay.py` accepts reviewed financial-cell mappings
from SEC, issuers or accessible vendors. This is an offline adapter, not an
automatic filing extractor or a Morningstar subscription. Save each actual source
file and a JSON overlay with `schema_version: 1`, `base_input_sha256`,
`information_cutoff`, `source_policy`, `scope`, `unresolved_gaps`, `sources`, `changes`.
The source policy must be chosen before inspection of resulting scores, prefer
latest primary evidence and be applied consistently to comparable issuers.

Each source needs `id`, HTTPS `url`, `kind` (`issuer`, `regulator`, `vendor`),
`published_at`, `retrieved_at`, relative `file`, and `content_sha256`.
If retrieved after the cutoff, retain the actual timestamp and require explicit
`point_in_time_evidence` for its pre-cutoff content; subsequent facts cannot enter.
Each change needs `symbol`, `table` (`income`, `balance`, `cashflow`), canonical
`field`, `period_end`, `old_value` (null for a newly added cell), `value`,
`basis: "GAAP"`, `currency: "USD"`, `units: "USD"`, `duration` (`quarter` for flows,
`instant` for balances), `source_ids`, `locator`, `derivation`,
`conflict_reviewed: true`, and `choice_reason`. The helper lists allowed fields.
Document any year-to-date subtraction, scale conversion and fiscal-calendar bridge.
Do not substitute adjusted EBITDA for operating income or net capex for gross
capex. Missing fields remain missing; do not default to zero. Non-USD and specialized
accounting still require their separate adapters. Preserve quote/EV inconsistencies
as gaps; this adapter updates financial cells, not all market-data feeds.

```text
python scripts/research_source_overlay.py /run/snapshot.json /run/overlay.json /run/sources /run/corrected-snapshot.json
```

The output preserves every original row and membership, adds correction provenance,
and never overwrites the original snapshot. Rerun the full score on this output,
not only the changed issuer. Retain the base snapshot, overlay and source bytes so
the other model can independently replay the correction. Bind the freshness ledger
with `source_overlay_sha256` and `corrected_input_sha256`, and regenerate row hashes.
Source-byte verification and input binding do not validate extraction judgments:
review the locators and arithmetic. Label the result as a **multi-source corrected
vendor baseline**, not an entirely filing-verified universe. A shared correction
replay and independent source acquisition are separate tests.

## Compute, do not substitute, the final order

```text
python scripts/research_handoff.py evaluate /run/contract.json /run/decision.json --snapshot /run/snapshot.json --ledger /run/freshness.json --review /run/screen-input.json --source-root /run/sources
```

Omit `--review` only for an honestly incomplete research checkpoint. The helper
recomputes the public queue, binds freshness to exact input rows, invokes the
existing primary/horizon review, and walks the queue in score order. Higher-ranked
unresolved cases block final selections; complete evidenced rejections can be
passed over. Ranking-relevant acquisition failures also prevent final selection even if all
reviewed candidates pass. The proposed final order cannot be rewritten by narrative preference.
Once the requested number has qualified, unresolved lower-ranked reviews do not
change the existing frontier rule; known stale data or ranking-relevant acquisition
failures anywhere still prevent completion. With no quota, or fewer choices than
requested, the frontier extends through the entire queue. All contenders must be
resolved and the universe fully scored before an exhaustive comparison can complete.
An unscored issuer cannot disappear merely because the scored subset was reviewed.

Results report `requested_count`, `requested_count_met`, `count_shortfall`,
`review_queue_exhausted` and `completion_basis`. A fully reviewed universe with only
two qualifying names may complete a three-choice request with two names and a
shortfall of one. A fully evidenced rejection of every name can complete with zero
selections; this is an exhausted research result, not a passing three-pick test.

Publish `research_candidates` and `selected_symbols` separately. Watch names are
not substitute buys. For no-quota mandates, the handoff passes the finite universe
size as an internal display bound to the unchanged public scorer; it is not an
invented user stock count and does not alter scores or profile weights.
Any separately requested discretionary alternative must be labeled nonconforming
to this selection test, with no overlap promise.

Retain contract, full snapshot, ledger, review document, decision output and source
bytes. Recompute in a separate output file and compare hashes before claiming
replay. For model comparison give both agents the same explicit mandate. Keep the
first output hidden until the other freezes its own result. Compare research-list
overlap, final-selection overlap, input differences, acquisition gaps and evidence
judgments separately. Shared-input execution is not independent acquisition; neither
establishes investment performance. For three picks, two shared names are 66.7%,
so an 80% threshold requires all three.

## Evidence quality rules

Do not label absent earnings dates as clear or outside the hold. Record estimated
and unknown events; compare their actual dates with the resolved entry/exit window.
Separate quarter flows from year-to-date totals with a sourced subtraction bridge.
Do not net pretax special items against after-tax income without a tax bridge, or
confuse revenue with cost reductions. Every evidence link must support the actual
claim. Templates copied from another issuer are not scenario evidence. Use the
computed gate reasons in the report: material risk alone does not prohibit a
Speculative candidate when that status is explicitly allowed. Never claim an audit
log or source file exists when it is absent from the deliverable. A three-name
review subset must not be presented as complete exchange-universe coverage.

## The remaining economic boundary

The public VQM baseline is research prioritization, not a validated one-month alpha
model. Its momentum window deliberately omits the most recent 21 sessions. A recent
earnings surprise or news event deserves primary review, but does not authorize an
unregistered momentum override. Longer-horizon valuation, high beta, analyst targets
and a GARCH fit do not establish one-month expected return. A new tactical strategy
requires a declared profile, point-in-time data, transaction costs, untouched
chronological validation and forward paper evidence before performance claims.

Research context: [NBER on analyst/investor biases and earnings drift](https://www.nber.org/reporter-2020-02/behavioral-biases-analysts-and-investors)
explains a possible mechanism, not validation of this package. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
distinguishes filing history from extracted facts; release exhibits and fiscal
periods still need review. Reproducibility fixes must not be marketed as proven alpha.
