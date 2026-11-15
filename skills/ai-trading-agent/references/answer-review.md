# Optional review of the delivered answer

Use `scripts/answer_review.py` when a researcher or buyer wants a retained,
itemized review of an actual answer. Ordinary research and delivery require no
reviewer, purchase, subscription or additional approval. The helper runs offline,
reads only explicitly named evidence and writes its result to stdout. It does not
dispatch a reviewer, run a study, grade campaign cases or authorize trades.

The existing [final report](final-report.md) and
[complete-delivery route](source-access.md#missing-access-and-useful-completion)
already verify their readable/structured bytes and supported calculations. This
optional layer records **declared judgments** against those exact delivered bytes
and a frozen request-bound unit list. It cannot decide whether arbitrary prose is
true, whether a source is authentic, or whether that list covers all user intent.

```console
python -B scripts/answer_review.py PRIVATE_ROOT/review.json --evidence-root PRIVATE_ROOT --protocol-sha256 EXTERNALLY_RETAINED_PROTOCOL_SHA256
```

Python API: `assess(document, evidence_root, expected_protocol_sha256)`.
The protocol hash must be independently retained by the caller; accepting a newly
edited protocol hash is a new adoption, not proof that the old threshold was met.
CLI exit 0 means `WITHIN_DECLARED_TOLERANCE`; exit 2 means escalation, incomplete
review, or invalid evidence. This is an advisory research-review outcome, not an
execution or institutional procurement gate.

## Bind the complete delivery and original inputs

The review document has exactly `schema_version: 1`, `protocol` (file reference),
`reviewed_at`, `reviewer`, `delivery`, and `reviews`. A file reference is exactly
`{path, sha256}`, with a relative forward-slash path beneath the explicit root.
Absolute paths, traversal, reparse points, named contact/configuration paths and
changed hashes are refused. Keep original files unchanged. No data is acquired.

`delivery` has exactly `kind`, `directory`, `receipt_sha256`,
`first_response_sha256`, `response_sha256`, `captured_at`:

| Kind | Existing verifier | Complete readable and structured answer |
|---|---|---|
| `canonical_response` | `final_report.verify_response` | `report/first-response.md` and `response.json` |
| `request_coverage` | `request_coverage.verify` | `first-response.md` and `response.json` |

Every listed file and the delivery receipt is hash-bound. The native verifier
checks the retained artifact inventory and regenerates both outputs. An unchanged
numerical annex does not verify surrounding prose: select the **whole** mixed
`request_coverage` delivery when that is what the user receives. Other answer
formats remain unsupported here; retain and review them separately without
claiming this result covers them. Do not create an irrelevant annex just to use
this helper.

`reviewer` is `{id, kind}`; kind is `human_reported`, `automated`, or `unknown`.
No human identity or activity is authenticated. All clocks include a timezone;
the declared protocol adoption must be no later than capture, and capture no
later than review. These declarations do not prove prospective registration.

## Adopt units and an absolute tolerance

The separate protocol file has exactly:

```json
{
  "schema_version": 1,
  "id": "desk-answer-check",
  "adopted_at": "2032-01-01T09:00:00Z",
  "original_request": {"path": "originals/request.json", "sha256": "ACTUAL_SHA256"},
  "sources": [{"id": "disclosure", "artifact": {"path": "originals/disclosure.json", "sha256": "ACTUAL_SHA256"}}],
  "units": [{
    "id": "reported-period",
    "requirement": "Retain the requested measurement period and distinguish it from retrieval time.",
    "request_spans": [{"start_byte": 0, "end_byte": 30, "sha256": "ACTUAL_SPAN_SHA256"}],
    "required_source_ids": ["disclosure"]
  }],
  "max_material_error_units": 0
}
```

Replace illustrative offsets and hash placeholders with actual retained bytes.
Each span is exactly `{start_byte, end_byte, sha256}`: nonempty UTF-8 byte offsets,
end exclusive, with the SHA256 of that slice. Partial UTF-8 characters are rejected.
Every unit refers to actual original-request spans. Original request and source
hashes must occur in the verified delivery's original-input inventory. This binds
bytes, not the semantic relevance of the selected passages or an independent source.

Use separate units for the task's material distinctions: unknown versus assumed
currency, measurement period versus retrieval time, amount attribution, supplied
but unreviewed evidence, contradictory interpretation, and relevant alternatives.
Choose applicable units before observing outcomes; these are examples, not a
universal rubric. There are at most 1,000 units, 128 sources, 32 spans per field,
16 MiB per referenced file and 64 MiB of directly referenced bytes. Existing
delivery verifiers retain their own artifact limits.

## Record judgments without concealing omissions

Each `reviews` row has exactly `unit_id`, `status`, `material_error`, `issues`,
`rationale`, `answer_spans`, `source_reviews`. For example:

```json
{
  "unit_id": "reported-period",
  "status": "MATERIAL_ERROR",
  "material_error": true,
  "issues": ["period", "attribution"],
  "rationale": "Reviewer judgment: the answer attributes an annual amount to the latest quarter.",
  "answer_spans": [{"artifact": "first_response", "span": {"start_byte": 50, "end_byte": 80, "sha256": "ACTUAL_SPAN_SHA256"}}],
  "source_reviews": [{"source_id": "disclosure", "status": "REVIEWED", "spans": [{"start_byte": 20, "end_byte": 60, "sha256": "ACTUAL_SPAN_SHA256"}]}]
}
```

Statuses are `SATISFIED`, `MATERIAL_ERROR`, `UNSUPPORTED`, `OMITTED`, `UNREVIEWED`.
Materiality is a separate declared boolean; use null when unassessed. A satisfied
unit must declare false, a material-error unit true, and an unreviewed unit null.
An omission or unsupported conclusion may also be a material error: set true so
it enters the absolute error count. Null never becomes zero.

Issue categories are `currency`, `period`, `amount`, `attribution`, `source_status`,
`contradiction`, `omitted_alternative`, `other`. Multiple issues in one unit still
count as one materially erroneous unit. `rationale` is explicitly reviewer prose,
not a generated financial claim. Located answer artifacts are `first_response`
or `response`; omissions and unreviewed units can have no answer span.

Every required source gets one disposition: `REVIEWED` with actual source spans,
or `SUPPLIED_UNREVIEWED` with no spans. Supplied-but-unreviewed evidence cannot
support `SATISFIED` or prove absence. Unknown/missing review units stay visible;
duplicate or unregistered units, changed pins and invalid locators are rejected.

The result derives status counts and the number of distinct units declaring a
material error. `declared_material_error_tolerance_met` is null until every unit,
required source and materiality judgment is reviewed. Missing/unreviewed units or
sources yield `INCOMPLETE_DECLARED_REVIEW`. Complete reviews with an exceeded
error limit, any unsupported answer, or any omission yield `REQUIRES_ESCALATION`.
Only the remaining complete records yield `WITHIN_DECLARED_TOLERANCE`; all negative
judgments remain in the result even when the adopted nonzero tolerance is met.

The answer's correctness, request semantic completeness, source authenticity,
source absence, human activity and honest clocks remain **unverified** under every
status. A reviewer can be wrong; a populated checklist cannot certify judgment.
This record measures no work time or savings. [Institutional acceptance](institutional-acceptance.md)
keeps any matched benefit observations and their measurement-kind limits separate.
It does not automatically consume this review or change its existing schema. If
using these counts as separately declared value evidence, retain this assessment
and its input pins, bind the same unit roster and actual output, and explain the
mapping. Unsupported, omitted or unreviewed units are not satisfied checks or
favorable zero-error results; do not map incomparable semantics automatically.
