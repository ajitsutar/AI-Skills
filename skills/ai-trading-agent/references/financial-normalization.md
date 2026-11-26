# Shared financial normalization

For new fundamental research use snapshot schema 2 with an embedded
`financial_normalization` input. Run the same shipped code in every model host.
The factor formulas remain `vqm-fundamental 1.0.0`; input interpretation is now
versioned separately by [financial-normalization 1.0.0](../profiles/financial-normalization-v1.json).
Both hashes identify the methodology. Never compare results across accounting
policy changes as though the inputs were unchanged.

Raw observations need not arrive preformatted as a normalization input. Use
`data.normalize_flows` with the [explicit flow mapping](flow-normalization.md)
contract to retain source bytes, periods, units, precision and reviewed concept
mappings, then delegate to this same normalizer. Missing mappings are mapping
work; do not substitute a model-written TTM formula or invent source verification.
The normalization input itself is schema 1; snapshot schema 2 embeds that input.

## Research a set of finalists

Run one request for the entire finalist set. Replace the fictional CIKs, dates,
and adapters with the approved issuer mapping and cutoff. Include explicit tag
and unit selectors that occur in the filings relevant to the mandate. Originals
can contain other supported tags. Use supplied SEC nightly archives or acquire
them once with an explicitly selected private output directory. These downloads
can occupy several gigabytes. The identifying SEC User-Agent belongs in the
private runtime variable `AI_TRADING_SEC_USER_AGENT`. A retained archive and
retained originals permit offline replay. [SEC bulk archive documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

A partial bulk download preserves each completed archive and its receipt. To
retry, supply the missing archive separately or choose a fresh private output
directory. File creation is exclusive. Review the provider response before
starting a new acquisition after denial.

```text
python scripts/finalist_filings.py fetch-bulk PRIVATE_BULK
python scripts/finalist_filings.py finalists.json PRIVATE_BULK/companyfacts.zip PRIVATE_BULK/submissions.zip PRIVATE_RUN --fetch-documents
```

The [fictional request](../examples/fictional-finalist-filings.json) shows the
input shape. The default selects the eight most recent eligible accessions
containing requested facts for each CIK. Amendments count toward that bound.
Set an issuer's `accessions` list to select specific eligible filings when
dates, restatements, or coverage require a different set. The companyfacts API
supplies discovery rows. The submissions index supplies the accession, form,
filing date, and official primary-document location. A filing known only by date
enters the selection on the following New York calendar day. The current bulk
archives can omit historical or subsequently corrected rows. Preserve the
actual archive receipts and describe any limits on reconstructing the cutoff.

Each external CIK directory holds the discovered candidates, specific filing
bytes and extraction receipts when available, replayable normalization input,
field results, and a review. `batch-review.json` preserves one outcome for
every valid requested issuer, including unavailable originals. A provider denial
halts subsequent network requests. To replay retained originals, replace
`--fetch-documents` with `--originals PRIVATE_ORIGINALS` and arrange files as
`CIK##########/ACCESSION/INDEXED_FILENAME`. For each source independently
matched to the primary, record `reviewed_originals[ACCESSION]` with its exact
SEC `url`, byte `sha256`, and `evidence`. A candidate-only pass omits both
options.

The issuer flag becomes `FILING_VERIFIED` only after the selected originals
match their sourcing route and every adapter field and the latest-public-period
review are ready. Include `latest_public_period_review` and any necessary
`reviewed_transcriptions` in the issuer request using the normalization schema
described below. Cite actual filing sections and accounting-basis evidence.
Inspect individual field gaps before ranking. Store vendor-only results on a
separate basis labeled `VENDOR_APPROXIMATION_NOT_FILING_VERIFIED`.

## Revenue trends and vendor fields

For a strict year-over-year TTM revenue rule, retain at least eight complete,
consecutive fiscal quarters or two independently reconciled adjacent full-year
windows. Check fiscal endpoints, unit/currency, consolidation and publication
cutoff before dividing current TTM revenue by prior TTM revenue and subtracting
one. Record both sums and their source IDs. Stop on missing quarters, mixed
bases, or a nonpositive denominator. Four to six quarters leave this rule
unevaluated unless there is an admissible full-year reconciliation.

If the mandate expressly permits a proxy, name the field when freezing the rule.
Use `--revenue-trend-proxy revenueQuarterlyGrowth` or
`--revenue-trend-proxy revenueGrowth` on the vendor helper. Only the named field
can contribute to the proxy. An absent quarterly field remains unavailable even
when general revenue growth is populated. Report the provider period if known,
the observed fraction, and `VENDOR_APPROXIMATION_NOT_FILING_VERIFIED`. The
proxy always records `strict_ttm_gate_satisfied: false`.

```text
python scripts/research_data.py vendor-finalist SYMBOL PRIVATE_VENDOR
python scripts/vendor_observations.py PRIVATE_VENDOR/vendor-input.json --revenue-trend-proxy revenueGrowth
```

At capture, preserve the source snapshot, component retrieval times, provider
version and errors. Replaying a current vendor observation as earlier knowledge
requires independent availability evidence. The adapter keeps reported values
and units, divides `debtToEquity` percent by 100, requires
`regularMarketPrice` and `marketCap` for rescaling, selects company growth
from the `+1y` row, and reads analyst counts from the explicit `0m` period.
Missing fields leave the corresponding gate unevaluated. The bundled contract
fixture exercises both normal and string-serialized values for offline preflight.

## Run the pipeline

From the skill directory, with a user-chosen output directory outside the skill:

```text
python scripts/filing_extract.py retained-filing.htm retained-extract.json
python scripts/financial_normalize.py normalize financial-input.json --output normalized-review.json
python scripts/financial_normalize.py verify normalized-review.json
python scripts/financial_normalize.py diagnose snapshot.json --output data-gaps.json
python scripts/vqm_research.py snapshot.json
python scripts/research_bundle.py create research-input.json research-bundle.json
python scripts/research_bundle.py verify research-bundle.json
```

Use [the complete fictional schema-2 snapshot](../examples/fictional-normalized-snapshot.json)
and [research input](../examples/fictional-normalized-screen.json) for executable
examples. They contain invented data and explicit zero observations, not approved
defaults or real research. Generated files use exclusive creation to avoid
overwriting evidence. No helper downloads sources, authenticates an account or
places orders.

If the VQM CLI fails because `exchange_calendars` is unavailable, it may also
emit a selected-snapshot diagnostic while retaining the original exception and
nonzero exit. This is not a computed score or ranking. Supported schema-1
snapshots retain their raw-byte hash and packaged profile identity, distinguish
publication and trailing-period policy, and keep share/EPS interpretations
conditional. Full original ingress is `NOT_BOUND`. The diagnostic does not
normalize schema 2; unsupported diagnostic inputs remain explicitly unavailable.
Successful calculations and other native failures keep their existing behavior.

For a supplied schema-1 snapshot audit that does not need a score, use the
[direct VQM observation operation](source-claims.md#selected-vqm-snapshot-observations)
with the complete original ingress and its fixed hash. It produces all selected
aggregate ratio rows without a calendar dependency. Retain its result and original
artifacts, then use the [typed observation renderer](report-claims.md#vqm-snapshot-observation-renderer)
and saved-report audit for a fixed report region. The existing `final_report`
`source_report` producer accepts this `source_claims` request; arbitrary authored
interpretation remains outside the typed region's contract.

## Evidence input

The `financial_normalization` object contains:

- `schema_version: 1`, `policy_sha256`, `information_cutoff`.
- `sources`: unique `source_id`, `document_origin` (`regulatory_filing` or
  `issuer_release`), `delivery` (`regulator`, `issuer`, `mirror`),
  `distribution_host`, `uri`, original-byte `content_sha256`, `retrieved_at`,
  `publication`, and `verification` with status, method and evidence references.
- `documents`: `source_id`, an embedded `extract`, and its canonical
  `extract_sha256`. The source carries that same extract hash. Hash with
  `deterministic_rank.digest`; do not confuse this canonical object hash with an
  original file-byte hash. The extract has `extract_schema_version: 2`, `contexts`,
  `units` and `numeric_inline_facts`; `filing_extract.py` creates this supported
  format. Context/unit nodes retain expanded element names and in-scope namespace
  bindings. Do not construct those bindings from a prefix guess.
- `transcriptions`: only for supported named accounting concepts not represented
  by an automatically mapped undimensioned standard tag. Retain a unique
  `record_id`, `source_id`, exact `entity_id`, `concept: reviewed:<name>`, `unit:
  USD`, period dates, accuracy (`decimals`), precise table/page/row/column `locator`,
  source `quote`, and `review` with `status: reviewed`, `policy_sha256`, and
  `basis_evidence`. Concepts and definitions are enumerated in the policy file.
  Concepts in `required_bases` also require the exact `basis` code from that map.
  For example, both `cet1` and `risk_weighted_assets` require `standardized`;
  `ffo_common` requires `nareit_unadjusted_common`. Missing codes fail validation;
  an explicitly different basis is excluded with a diagnostic, never substituted.
- `issuers`: unique `issuer_id`, exact `entity_id`, accounting `adapter`,
  `ttm_start`, `financial_period_end`, optional dated `predecessors`, and
  `latest_public_period_review` with cutoff, period, source IDs and evidence.
  Use `status: unresolved` until that latest-period check is actually done.

A transcription supplies either an absolute-dollar decimal `value` or a
`display_text` cell with `format`, `scale`, optional `sign`, and `decimals`.
The latter makes the shared parser perform thousands/millions conversion. Do not
supply both. A duration observation includes `period_start`; an instant omits it.
No arbitrary expressions, executable mappings or model-calculated TTM estimates
are accepted. Record individual reported legs and let the helper combine them.

An unsupported extension/dimension or PDF table needs one reviewed transcription,
saved in the shared input for all models. That interpretation remains a human or
model research judgment; recording a review status does not prove it. Models may
propose a correction with evidence, but must create a separate input revision.
They must not silently replace the shared ledger to obtain a preferred ranking.

## Recovery backlog: separate calculation support from source assurance

Classify each field on separate axes when diagnosing or recovering data:

| Axis | Record the actual finding |
|---|---|
| Value availability | Supplied observation, successfully derived value, or absent operand; retain its source/result pointer. Inspect embedded normalization inputs as well as materialized rows. |
| Normalization support | Whether this implementation supports the concept, adapter, unit, period path and input representation; cite a concrete unsupported feature or diagnostic when it does not. |
| Executed calculation | Preserve the normalizer's actual result, status, issues and calculation trail, including READY, draft or unresolved output. |
| Documentary assurance | Whether original source bytes, identity, publication, period and verification evidence are retained and independently checked; distinguish declarations from checks performed. |

A supported reviewed transcription remains a supported input representation even
when the original filing is not supplied. A successful normalization does not
authenticate that transcription. Missing original bytes create a source-recovery
or verification gap; they do not by themselves make its format, concept or
calculation unsupported. Conversely, READY or a supplied verification flag cannot
close a documentary assurance gap that has not been checked.

Keep these findings together in the backlog. Preserve a computed value and its
limitations rather than rewriting it as absent or changing the helper's status.
For an unsupported mapping, identify the unsupported element and the supported
reviewed-transcription or adapter work needed. For an absent observation, identify
the missing operand. For missing original bytes, request or acquire the specific
document and verify/re-extract it when authorized. These are distinct recovery
actions; more than one can apply to a field. An unavailable source does not prove
that no value exists, and a value's presence does not establish eligibility for
real research. Fictional declarations remain fictional even when replay succeeds.

## Frozen accounting choices

- Operating income means the reported GAAP operating-income line. No automatic
  EBIT reconstruction from pretax income or discretionary addbacks.
- `net_income_ttm` uses income attributable to the parent, not consolidated
  `ProfitLoss` including NCI or income after preferred dividends. This is an
  explicit factor convention; the CFO-minus-income metric retains that convention
  and is not a full reconciliation of consolidated accruals. Common earnings in
  bank/insurer/other-financial adapters are after preferred dividends.
- Cash is cash and cash equivalents. Short-term investments, restricted cash and
  equity investments are excluded from this policy.
- Debt sums four disjoint reported components: current borrowings, noncurrent
  borrowings, current finance leases, noncurrent finance leases. The first two
  exclude finance leases. A tag whose scope is unclear needs reviewed evidence;
  do not add an aggregate and its included components.
- Corporate productive capex is gross cash PP&E purchases plus separately
  capitalized productive assets not already included. REIT capex uses gross
  property-asset purchases, development/improvements and other productive
  capitalization. Exclude business combinations, noncash items and sale proceeds.
  Each component must be observed, including evidenced zero where appropriate.
- Bank capital uses the Standardized approach. Tangible common equity is at
  period end with the policy's intangible/deferred-tax treatment. The loan-risk
  ratio uses nonaccrual retained amortized-cost loans over gross retained
  amortized-cost loans before allowance, with matching scope. It is not NPA/loans.
- Equity REIT FFO is unadjusted Nareit FFO attributable to common, not normalized,
  adjusted, diluted or AFFO. Confirm the issuer's definition and reconciliation.
  For FFO/AFFO/CFO reporting comparisons, use the separate
  [REIT reconciliation helper](reit-reconciliation.md). A numerical difference
  does not identify recurring capex within gross-capex categories; that helper
  preserves missing overlap mapping without changing normalization policy.

Policy changes require a new version, hash and complete rerun. Missing fields
remain missing; the package does not infer zero from absence of a tag.

## Periods, precision, sources and identity

The parser requires well-formed XHTML, rejects DTD/entity declarations, and
resolves namespace URIs for inline elements, contexts, units, monetary measures,
fact concepts and transformation names. Prefix aliases and local rebindings are
preserved. Automatic financial mapping supports the annual FASB US-GAAP namespace
(`http://fasb.org/us-gaap/YYYY`) and ISO 4217 USD. A custom namespace does not
become US GAAP by using the `us-gaap` prefix. Legacy extracts without bindings
must be regenerated from original filing bytes; no prefix assumptions are added.

The parser resolves a unit's measure, not its arbitrary unit ID. It applies
supported numeric transforms, sign and scale; `decimals` describes reporting
accuracy and does not scale a value. It conservatively excludes dimensioned facts,
unsupported transformations, continuations, exclusions and non-USD units from
automatic mapping. It is a supported subset, not a complete XBRL conformance tool.
Use the resulting extraction diagnostics to acquire/review missing observations.

TTM paths are exact direct periods, four contiguous fiscal quarters, or annual
plus current YTD minus prior YTD. Prior balance dates are the day before TTM starts.
Available admissible paths must reconcile within propagated rounding intervals.
For each component the policy first uses a complete verified path; unverified
observations are used for draft calculations only when no complete verified path
exists. A conflicting unverified mirror cannot displace a verified path.
Conflicting verified observations do not resolve through file order or a
favorable source choice, and remain unresolved even if a draft alternative exists.
Restatements and amendments public after cutoff cannot enter that snapshot.

`publication` is either `{precision: timestamp, at: <timezone-aware timestamp>}`
or `{precision: date, date: YYYY-MM-DD, timezone: <IANA zone>}`. Date precision is
a whole-day interval, bounded above by retained retrieval evidence. The complete
interval must precede cutoff; a same-day ambiguity is not backdated to midnight.
Generated scorer source timestamps are labeled conservative bounds, not claimed
SEC acceptance timestamps.

An issuer-hosted actual filing can be accepted with verified identity/content
evidence; a PDF rendition need not be byte-identical to SEC HTML. A mirror needs
recorded matching primary evidence. Unverified evidence can yield draft
calculations for inspection, but those values do not enter scoring.

`predecessors` contain the old `entity_id`, `successor_entity_id`,
`effective_date`, `reporting_basis_unchanged`, `source_ids`, and `evidence`.
The old entity's facts must end before the effective date. This does not certify
price-history continuity or corporate actions. A URL directory alone is not an
entity mapping. Unverified mapping evidence keeps the derived fields in draft.

## Scorer and model parity

Schema-2 snapshot rows supply market data and security/industry identity. They
must not supply financial facts or derived financial metadata. The scorer reruns
the embedded normalization input, checks accounting-adapter alignment, and
materializes the financial fields itself. An attempted replacement value fails.
Draft source-dependent values remain absent from scoring. The original input,
policy, implementation and calculation trails are hashed and retained.

Schema 1 remains available for explicit legacy arithmetic diagnostics and labeled
fictional regression examples. New real research through `prepare_document`/
`research_bundle.py` requires schema 2. Do not label real inputs fictional to skip
normalization. Shared evidence decisions continue to be hashed separately by the
research bundle; numeric rank and eligibility decisions are distinct stages.

`diagnose` enumerates independent financial gaps and checked market prerequisites
without pretending verification passed. It is not a replacement for the complete
scorer, source review, event review, or universe-completeness checks. No shared
file supplies missing public data or establishes investment performance.

Same inputs and policy should give identical numeric output. Real stock-pick
overlap still requires two completed actual lists; synthetic tests, partial
normalization and matching failures cannot establish the 80% target.

## Technical references and provenance

The implementation is newly written for this repository using Python's standard
library and existing repository helpers. No third-party parser code or downloaded
Claude script was incorporated. Relevant standards and definitions:
[XBRL International's Inline XBRL primer](https://www.xbrl.org/specification/inlinexbrl-part0/rec-2013-11-18/inlinexbrl-part0-rec-2013-11-18.html),
[Inline XBRL specification index](https://specifications.xbrl.org/work-product-index-inline-xbrl-inline-xbrl-1.1.html),
and [Nareit FFO guidance](https://www.reit.com/nareit/advocacy/policy/nareit-ffo-white-paper-and-related-implementation).
The accounting choices above are package conventions, not a claim of universally
optimal financial ratios or full compliance with every filing taxonomy.
