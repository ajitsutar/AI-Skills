# Enforced research contract and final selection

Use this workflow for new ranked fundamental or dated stock-pick requests. It
closes the gap between a reproducible discovery score and discretionary final
tables. Intraday remains a separate registered-signal workflow. Do not reroute an
explicit momentum/other strategy to VQM; disclose when its requested implementation
is unavailable. An unspecified aggressive posture is not permission to invent
beta, analyst-count, price-momentum or earnings-blackout filters.

## Lock the actual mandate

Before selecting names, save a JSON object with `prompt`, `universe`, `hold`,
`count`, `capital`, `risk_posture`, `early_exit_policy`, `information_cutoff`,
`price_date`, `entry_at`, `exit_at`, `standing_preferences`, `earnings_policy`,
`selection_mode`, `allowed_statuses`, and `custom_filters`.

Resolve the horizon through horizon_review.py first. Timestamp fields must include
timezones. `count` is the user's requested number; there is no fixed skill quota.
`standing_preferences` is `ignore` only when requested, otherwise
`explicit_in_this_mandate`: copy applicable user instructions explicitly, never
silently inherit another model's assertions about standing rules.
`earnings_policy` is `allow_with_disclosure` or `exclude_during_hold` according to
the actual mandate. Neither research setting loosens live execution controls.
`selection_mode` is `computed_order`; `custom_filters` is `[]` for this shared
profile. `allowed_statuses` is `["Eligible"]`, or `["Eligible", "Speculative"]`
for an explicitly aggressive speculative research comparison. This is not a
claim that Speculative is suitable for a user with a guaranteed-loss constraint.

```text
python scripts/research_handoff.py lock /run/mandate.json /run/contract.json
```

The contract pins implementation hashes and profile. It grants no trading authority.
Changing its rules requires a new contract, not editing an already frozen run.
Complete packages must pass research_preflight.py, including manifest verification.
SKILL.md alone, stale agent entrypoints, or a version string without files do not
establish the installed implementation. Instructions cannot force a model to use
tools; require execution artifacts and reject unsubstantiated conformance claims.

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
Publish `research_candidates` and `selected_symbols` separately. An empty final
list is not a passing three-pick test, and Watch names are not substitute buys.
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
