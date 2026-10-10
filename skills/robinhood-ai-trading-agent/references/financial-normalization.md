# Shared financial normalization

For new fundamental research use snapshot schema 2 with an embedded
`financial_normalization` input. Run the same shipped code in every model host.
The factor formulas remain `vqm-fundamental 1.0.0`; input interpretation is now
versioned separately by [financial-normalization 1.0.0](../profiles/financial-normalization-v1.json).
Both hashes identify the methodology. Never compare results across accounting
policy changes as though the inputs were unchanged.

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
