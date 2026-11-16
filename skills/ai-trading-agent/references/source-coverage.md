# Exact-source coverage delivery

Use this route for a supplied-source information coverage map whose requested
topics need a complete readable/structured answer but are not fully represented
by a numerical producer. It delivers the actual whole answer from exact source
wording. It does not generate investment judgments, calculate unsupported facts,
acquire new sources or certify semantic completeness.

Read the complete original request and every allowed source first. Adopt a
scope before producing the answer: retain the request unchanged, its SHA256,
the complete original ingress manifest SHA256, and literal byte spans for the
requested topics. These are original-request spans, not an invented grading
rubric or a rewritten request. Each span records `id`, `start_byte`, `end_byte`
and `sha256`. The scope has exactly:

```json
{
  "schema_version": 1,
  "original_request": {"path": "request.txt", "sha256": "ACTUAL_SHA256"},
  "manifest_sha256": "ACTUAL_ORIGINAL_INGRESS_SHA256",
  "units": [{"id": "topic", "start_byte": 0, "end_byte": 10, "sha256": "ACTUAL_SPAN_SHA256"}]
}
```

Keep the adopted scope SHA256 and ingress SHA256 outside the generated delivery.
The coordinating workflow must bind the original corpus and requested topic
inventory independently; accepting participant-selected pins alone cannot detect
a substituted subset. Literal spans prove text identity, not full interpretation.

Author a plan containing every adopted topic and every original source once:

```json
{
  "schema_version": 1,
  "units": [{"unit_id": "topic", "source_ids": ["source-a"], "discovery_routes": ["ORIGINAL_PUBLISHER"]}],
  "sources": [{"source_id": "source-a", "access": "SUPPLIED_EXCERPT", "lineage": []}]
}
```

Select the original sources relevant to each topic. Sources may serve multiple
topics. Selection retains each entire original text, including qualifiers,
dates, dependencies and competing details, rather than taking a convenient
numeric fragment. No authored fact, quote override, summary, amount, currency,
period or topic label is accepted in this plan. Original source assertions are
attributed evidence, not newly authenticated facts. Unselected sources still
appear in the complete inventory. All UTF-8 text/JSON sources remain byte-bound
and retained privately; sources outside the manifest are never silently added.

Access declarations are `SUPPLIED_BODY`, `SUPPLIED_EXCERPT`,
`RESTRICTED_ACCESS_NOTICE`, `SEARCH_DISPLAY`, `INDEX_PAGE` or `UNCLASSIFIED`.
Lineage rows contain exactly `source_id` and `relation`; relations are
`REPOST_OF`, `QUOTES`, `REFERS_TO` or `RELATED_UNVERIFIED`. These labels are
participant declarations and can be wrong. Do not infer independent provenance
from two URLs, a date from file time, or full access from a search display.
Keep ambiguous access/lineage unclassified or explicitly unverified.

Discovery routes are `ISSUER_INVESTOR_RELATIONS`, `REGULATOR_FILINGS`,
`EXCHANGE_DISCLOSURES`, `ORIGINAL_PUBLISHER` and `PUBLIC_SEARCH`. Every route
is a prospective plan marked `NOT_EXECUTED`. The helper does not browse. When
acquisition is excluded, this is the limit of discovery. When acquisition is
authorized and needed, execute permitted host tools, retain their actual original
results, and adopt a new complete corpus before generating a new delivery.
Never describe a plan as completed research or bypass access restrictions.

```sh
python -B scripts/source_coverage.py compose /private/plan.json --scope /private/scope.json --scope-sha256 SCOPE_SHA256 --manifest /private/ingress.json --manifest-sha256 ORIGINAL_INGRESS_SHA256 --source-root /private/sources --output /private/coverage
python -B scripts/source_coverage.py verify /private/coverage --scope-sha256 SCOPE_SHA256 --manifest-sha256 ORIGINAL_INGRESS_SHA256 --first-response /private/coverage/first-response.md --response /private/coverage/response.json
```

The output directory must be new and outside the skill. An optional `--metadata`
uses the existing final-report response metadata schema for case/model/runtime
declarations; these do not carry analytical claims. Both answer files derive
from the same retained request, source bytes and plan. Verification re-renders
both, checks all retained files, pins the implementation and version, and can
compare the exact published pair. Preserve the entire output directory for replay.

Deliver the generated `first-response.md` and `response.json` unchanged as the
actual complete answer, not as an annex to an independently authored summary.
Use an artifact status/link-only chat cover note. Do not add an unbound factual
summary that can contradict the files. Keep any actual cover note in evaluation
evidence; an unsupported statement there is still an answer defect.

The map is explicitly partial: missing selected evidence means unresolved
coverage, not no activity, zero or source absence. Every requested topic remains
visible even when no source is selected. No source currency, amount, period or
current status propagates into another source or period. The helper neither
proves that selected sources are relevant nor that all requested analysis was
completed. Use [answer review](answer-review.md) for declared source-aware
findings on the actual pair, preserving its first bytes and negative findings.
Review must not relabel literal replay as truth or silently replace the original
answer. Corrections belong in a separately labelled new delivery.

For supported rating, target and estimate revision questions, adopt `analysis_profile: ANALYST_REVISIONS` in the external scope and follow [analyst revision delivery](analyst-revisions.md). The whole generated pair includes native metric-specific analysis computed directly from the pinned originals. The plan accepts no precomputed analysis or factual override. The default `EXACT_SOURCE_ONLY` profile retains the original quotation-only behavior.

## Explicit topic gaps and acquisition needs

Each topic plan row may include `gaps`. An externally adopted scope can set
`require_topic_gap_declarations: true`, requiring that field on every row.
An empty list means no gap was declared, not complete evidence. Keep supported
original facts separate from missing dimensions or policy/access questions.
Each gap has exactly:

```json
{
  "requested_evidence_dimension": "original measurement convention",
  "reason": "MISSING_ORIGINAL_DOCUMENT",
  "reviewed_source_ids": ["source-a"],
  "source_spans": [],
  "acquisition_route": "ORIGINAL_PUBLISHER"
}
```

The dimension label names the evidence being requested, not a factual claim.
Use a short nonnumeric subject label (ASCII letters, spaces, underscores,
slashes or hyphens, maximum 120 characters), never factual prose or an amount.
The helper validates syntax, not whether a label is sensible or honestly chosen.
All labels render as literal requested-evidence data and remain visibly
participant-declared/unverified. No authored factual override is permitted.

Reasons are `MISSING_CURRENT_OBSERVATION`, `MISSING_ORIGINAL_DOCUMENT`,
`MISSING_POLICY_DISCLOSURE`, `MISSING_BASIS_OR_PERIOD`, `INCOMPLETE_ACCESS`,
`UNRESOLVED_LINEAGE` or `UNREVIEWED`. These express a participant's unresolved
evidence need, not an independently verified absence. Reviewed source IDs must
belong to the complete original corpus. An optional supporting `source_spans`
row contains exactly `source_id`, `start_byte`, `end_byte`, and `sha256`; its
UTF-8 byte span must match a source declared reviewed. The exact passage is
rendered separately from the declaration. A source span cannot prove a general
absence outside its scope; no supplied span means no quoted support.

`acquisition_route` uses the existing prospective route enum. Every proposed
acquisition remains `NOT_EXECUTED`, and every gap sets source-absence proof
false. Describe concrete unresolved evidence dimensions while retaining the
current source facts; do not invent missing source content, claim a completed
search, or require a paid account. The whole original request, source inventory,
first pair and negative review remain preserved.

For requested insider-row or institution-snapshot analysis covered by the native profile (not merely mixed inputs containing those rows), `analysis_profile: INSIDER_DISCLOSURES` invokes [source-bound insider disclosure delivery](insider-disclosures.md) in the complete pair. It preserves original row-local units and mechanisms without importing currency or ownership from other original contexts.

For political or other public claims about a disclosed trade, follow [disclosure claim analysis](disclosure-claims.md). Neither exact source quotation nor the insider profile assesses unsupported claim components. Deliver the complete authored analysis through the existing review cycle, retaining any relevant native output as an annex.
