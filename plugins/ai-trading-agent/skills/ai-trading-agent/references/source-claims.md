# Source-bound claims and configured corpus coverage

Use `scripts/source_claims.py` when interpreting an unbound adapter field, naming
EPS from raw accounting operands, or claiming that a selected analyst cohort
accounts for the supplied source corpus. This companion produces executable
claim checks; it does not replace arithmetic, original-source review or existing
analyst eligibility rules.

## Trust boundary and invocation

Use the complete original-source ingress manifest and its externally fixed hash,
as specified in [original-source-lineage.md](original-source-lineage.md). Do not
create a smaller manifest containing only files selected for an analysis and
then call that the supplied corpus. Every source in the manifest is verified.
All formats must be supported before a corpus scan can be reconciled. A source
of format `bytes` remains an explicit unsupported gap; it is never skipped as
irrelevant. JSON sources reject duplicate keys and nonfinite numbers.

```text
python -B scripts/source_claims.py --manifest ingress.json --manifest-sha256 PIN --source-root originals --input claim-request.json --output claim-result.json
```

Output creation is exclusive. A rejected `assert_claims` request writes the
machine-readable report and exits 2; invalid references or inputs raise an error.
Retain both results and failed commands. The Python interface is
`audit(request, manifest_path, expected_manifest_sha256, source_root=None)`.

The response contains `facts`, `allowed_claims`, `unsupported_claims`,
`claim_verdict`, the input/implementation/manifest hashes and an operation-specific
result. Use those facts in the final answer. `WITHIN_DECLARED_CONTRACT` means no
requested claim exceeded that operation's contract; it is not a correctness
grade, source authentication or a statement that unavailable calculations ran.

## Exact references

A JSON scalar reference is `{"source_id":"filing","pointer":"/shares/value"}`.
A text reference is `{"source_id":"note","start":0,"end":12,"excerpt":"exact bytes…"}`,
with actual matching text and character offsets. Offsets address the UTF-8-sig
decoded source string, not raw byte offsets. The entire excerpt must match at
that position; a matching quote elsewhere is insufficient. References resolve
only inside the pinned manifest.

For a JSON document embedded in a text file, supply `start`, `end`, and `excerpt`
for that complete JSON segment and add `pointer`. The selected segment is parsed
strictly and the pointer resolved within it. This explicit binding preserves any
header, raw source bytes and surrounding context; there is no guessed extraction
of the first brace, synonym parser, parent inheritance or source overwrite.

## Presence and adapter identity are separate

```json
{
  "operation": "presence",
  "terms": ["common"],
  "match": "any",
  "assert_claims": ["source_candidate_present"]
}
```

Terms are configurable token phrases, matched case-insensitively against all
text lines or JSON leaf paths and scalar values. Underscores and camel case in
keys are token separators. `match` is `any` (default) or `all` within a candidate.
All matching candidates retain exact references, source hashes and values.

An optional `binding` is `{"value":"common","source_ref":{...}}`. Its state
is independently `UNBOUND`, `EXACT_SOURCE_VALUE`, `SOURCE_VALUE_NULL` or
`INVALID`. A matching source label can therefore coexist with an unbound adapter
field. Report both facts. Do not turn `UNBOUND` or `INVALID` into “the source did
not supply it.” A candidate label is also not automatically established semantic
metadata or an authenticated holder basis.

Allowed assertions are `source_candidate_present` (when there are candidates)
and `adapter_value_bound` (when an exact non-null value is bound). `source_absent`
is never authorized by this lexical tool, even after zero hits: absence of the
configured phrase does not establish absence of equivalent meaning.

## Typed accounting claims

Use `operation: "accounting"` with `income` and `shares` objects whose fields
are exact source references, not copied values or unanchored declarations:

| Object | Required scalar fields |
| --- | --- |
| income | value, attribution, period_start, period_end, issuer, currency, unit_scale |
| shares | value, basis, period_start, period_end, issuer, unit_scale |

`unit_scale` is the positive multiplier from the reported number to actual
currency units or actual share count. For example, 1000 means thousands. Periods
must be valid ISO dates and identical across operands; issuers must match.
Currency must be an explicit three-letter uppercase code. A missing scale or
period is not silently assumed.

Supported explicit type pairs are:

| shares.basis | income.attribution | Allowed assertion |
| --- | --- | --- |
| weighted_average_basic | income_available_to_common | basic_eps |
| weighted_average_diluted | diluted_income_available_to_common | diluted_eps |

These strings must be bound to original leaves, not fabricated as adapter
metadata. The contract deliberately does not infer common attribution from
consolidated net income, diluted numerator adjustments from a generic numerator,
or period weighting from a share count dated at period end. Other source wording
can be reviewed qualitatively, but cannot acquire exact typed-source status by
merely renaming it.

Each operand's metadata must come from the same structured source object as its
value: same source, same explicitly selected JSON segment (if any), and same
parent JSON pointer. Metadata borrowed from another income/share record remains
a diagnostic-only mismatch, even if issuer and period strings happen to match.
Shared parent metadata is not automatically inherited. A source that lacks this
explicit association requires review; selecting a favorable scalar elsewhere
cannot manufacture the association.
Each pointer must also end in its canonical role name (`value`, `attribution`,
`basis`, and so on). A numeric sibling such as `consolidated_income` cannot borrow
the common attribution attached to the object's `value`. Arbitrary source aliases
remain diagnostic-only; this operation checks canonical typed operand records,
not inferred accounting relationships in an arbitrary financial document.

When numeric operands exist, `raw_operand_ratio` preserves their arithmetic even
when metadata is missing or incompatible; it explicitly has no unit-scale
adjustment. Such a result is `DIAGNOSTIC_RATIO_ONLY`, with `eps: null` and
specific reasons. When all required source-bound types and dimensions agree,
`eps = income.value * income.unit_scale / (shares.value * shares.unit_scale)`.
This is a source-bound calculation, not independent accounting verification.
`pe` remains null: no comparable quote is accepted by this operation. Never
derive standard P/E from a diagnostic raw-operand ratio.

## Configured source corpus coverage

Start with `operation: "coverage"`, `terms` and an empty `dispositions` list to
discover candidates across every pinned source. File names never determine
eligibility. The result returns stable `candidate_id` values and original source
references; it will usually be `INCOMPLETE` on this first discovery call.

For each candidate, supply a disposition with exactly these fields:

```json
{
  "candidate_id": "ID_FROM_SCAN",
  "status": "extracted",
  "record_ids": ["target-record-a"],
  "reason": "Reviewed target disclosure; extraction retained"
}
```

Statuses are `extracted`, `reviewed_not_relevant`, and `unresolved`. Only
`extracted` accepts nonempty `record_ids`. Every disposition needs a reason.
For each extraction, include a record in `records`:
`{"record_id":"target-record-a","source_refs":[EXACT_CANDIDATE_REF]}`.
The reference must equal the candidate's original reference and resolve against
the pinned bytes. Duplicate/unknown candidate IDs, orphaned extraction records,
unresolved candidates or unsupported source formats cannot yield a reconciled
scan. A later revision in a different file is discovered by the same scan as an
older report; it cannot disappear just because its filename differs.

`CONFIGURED_SCAN_RECONCILED` authorizes only `configured_scan_reconciled`.
It never authorizes `complete_corpus`, universal semantic completeness, every
real-world analyst, or the truth of reviewer relevance judgments. Search terms
and `reviewed_not_relevant` reasons must be reviewed for suitability; this tool
cannot discover paraphrases outside those terms or prove a human/model judgment.

## Guarded analyst review

`operation: "analyst_corpus"` accepts `coverage` (the coverage request above)
and `analysis` (the existing `analyst_evidence.review` input). Individual-target
record IDs must match the coverage extraction record IDs exactly. Each target's
source path/hash must match the pinned manifest, and its cited excerpt must
include the exact linked text candidate. The tool blocks analysis while any
configured candidate or source remains unresolved.

Once coverage is reconciled, the wrapper runs the existing analyst eligibility,
date/conflict handling and latest-per-firm selection and retains both coverage
and analysis outputs. Numeric extraction, firm identity, issued dates and
relevance remain explicit reviewer judgments governed by that helper's contract.
A successful latest selection is scoped to the source-bound extracted records
and declared search, not to a magically complete global corpus. Preserve every
excluded row and avoid promoting conditional cohort results to all supplied
meaning when a scan cannot support that scope.

The CLI parses decimal JSON tokens without silent source rounding. For the
existing float-based analyst helper, it converts a decimal only if the finite
float's shortest decimal text round-trips to the original decimal value;
unsupported precision raises an explicit error instead of excluding a valid row
or silently changing a target. The conversion boundary is retained in the result.

Tests: `python -B -m unittest discover -s tests -p test_source_claims.py -v`.
The module depends on the bundled `source_lineage.py`; guarded analyst review also
uses `analyst_evidence.py`. No network, broker, installation or live order occurs.
