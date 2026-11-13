# Compose and verify the final research artifact

Use `final_report.py` when the supported source reports, accounting claims or
terminal objective diagnostics should become the saved answer. It executes and
replays the existing producers and writes one exact `first-response.md`. It does
not acquire sources, infer missing metadata or grade arbitrary prose.

```console
python -B scripts/final_report.py compose plan.json --manifest SOURCE-INGRESS.json --manifest-sha256 EXTERNAL_PIN --source-root ORIGINAL_ROOT --output NEW_DIRECTORY
python -B scripts/final_report.py verify NEW_DIRECTORY --final-response SAVED_FIRST_RESPONSE.md
```

The output directory must not exist and must be outside the skill. Preserve
failed attempts; `failure.json` records the failed stage without claiming a
completed response. Do not overwrite an earlier first response. Publication or
capture must use the generated file's unchanged bytes.

`compose` prepares and replays the selected operations before creating any final
answer. Under `STRUCTURED_RESEARCH_ONLY`, every selected terminal section must
execute with job status `COMPUTED`. A missing/unsupported input role or another
input/execution rejection leaves the original plan, corpus, workflow arguments,
result/reason and `failure.json` as preparation diagnostics; it creates no
`first-response.md`, `analysis.json` or canonical response envelope. Declare a
supported role using an original source binding or an explicit assumption and
run the corrected plan in a **new** directory. The tool never infers a role,
fills an input or turns a rejected job into a completed calculation. Original
failed attempts and previously saved first responses remain immutable.

Execution readiness is not an economic success criterion. Negative returns,
unattainable boundaries, DCF `NOT_EVALUATED`, missing EPS, unknown dates and
conditional source findings remain valid reportable outcomes of supported
executed producers. There is no required/optional terminal override in strict
mode. For a diagnostic or blocker investigation, use the retained preparation
artifacts or the existing legacy diagnostic contract; a legacy rejected result
cannot be exported as a completed strict canonical response.

For explicit inspection before finalization, the optional two-step interface is:

```console
python -B scripts/final_report.py prepare plan.json --manifest SOURCE-INGRESS.json --manifest-sha256 EXTERNAL_PIN --source-root ORIGINAL_ROOT --output NEW_DIRECTORY
python -B scripts/final_report.py finalize NEW_DIRECTORY --preparation-sha256 PREPARATION_RECEIPT_PIN
```

The first call writes `preparation.json` and returns its `preparation_sha256`,
without a first response. The second requires that exact pin, unchanged retained
plan/corpus/implementation/results, and another source/calculation replay. It
refuses already finalized or failed preparations. Copying the whole prepared
directory preserves replay portability. Normal `compose` performs both steps;
no additional ceremony is required. Readiness policy `strict-terminal-execution-1`
also applies on strict replay and export. Historical artifacts remain reviewable
with their frozen version and implementation; they are never relabeled as new
preparations or retroactively upgraded by this policy.

The plan contains `sections` and optionally `unverified_prose` and the boolean
`objective_conclusion_required`. Every section is
rendered in order with its complete supported report and unresolved findings.
Caller-created output, status or report strings cannot substitute for execution.

```json
{
  "sections": [
    {
      "kind": "source_claim",
      "request": {"operation": "presence", "terms": ["common"]}
    }
  ]
}
```

Four section types are supported:

- `source_report`: exactly `kind`, `producer` and `request`. Producer is
  `analyst_sources`, `reit_sources` or `source_claims`. Request follows that
  producer's documented schema. The compositor calls the existing supplied
  research bridge and includes its whole generated report, with an evidence
  link to the complete result. It cannot hide an unsupported revision by
  selecting only a favorable sentence.
- `source_claim`: exactly `kind`, `request`, and optional `label` for accounting.
  Request is an existing `source_claims` accounting or presence request against
  the complete pinned corpus. The actual output is rendered through
  `report_claims`. Accounting label may be `diagnostic_ratio`, `basic_eps` or
  `diluted_eps`; an unsupported EPS label fails. Without a label, the actual
  source classification chooses supported EPS or diagnostic arithmetic. Dated
  shares and missing numerator attribution never become reported EPS or P/E.
  Presence preserves lexical candidates, unknown bindings and absence limits.
- `terminal_objectives`: exactly `kind`, `contract` and `document`. Contract is
  the existing research workflow contract. Document is its binding tree: each
  value is selected by `{"$source":{"id":"SOURCE_ID","pointer":"/path"}}`
  or marked `{"$assumption":VALUE,"reason":"Declared reason"}`. A complete
  model object may be selected at pointer `""`. At least one source binding is
  required. The full workflow source inventory is derived from the externally
  pinned manifest; callers cannot supply a smaller source list or other jobs.
  Only `financial.terminal_scenarios` runs. Its saved workflow is replayed and
  the computed result is compared with the native installed terminal helper.
  The complete objective report retains comparator identity, derived-probe
  assumptions and DCF-unavailable limits. Source binding establishes byte
  selection, not that caller-selected financial roles are correct.
- `objective_conclusion`: exactly `kind`, `evidence_section`, `objective_id`,
  `domain_scope`, and optional `research_judgment` and `include_boundaries`.
  `evidence_section` is the
  zero-based index of an earlier `terminal_objectives` section in this plan.
  The referenced source-bound workflow and native calculation are independently
  replayed again; a saved success flag or caller-authored outcome is insufficient.
  `domain_scope` must be `SUPPLIED_ROWS`. `objective_id` is either
  `AFTER_COST_CAPITAL_PRESERVATION` or `DCF_DISCOUNT_CLOSURE`.
  The former generates the exact comparator, horizon and passing, nonpassing
  and unresolved original scenario/declared-sensitivity rows. Derived probes
  remain separate; finite row outcomes never become general joint necessity.
  The latter generates `NOT_EVALUATED`: terminal evidence does not evaluate a
  DCF cash-flow model or closure criterion, even if every terminal row is positive.
  An unresolved terminal job establishes no passing or necessary conditions.
  Optional `research_judgment` is exactly `{"stance":"favorable"}`,
  `{"stance":"unfavorable"}` or `{"stance":"undetermined"}`. The fixed text
  labels that stance an analyst-selected, uncomputed opinion; it is never
  inferred from returns or presented as verified investment correctness.
  For capital preservation only, `include_boundaries: true` adds the actual
  conditional minimum from `solution.minimum_multiple`, with its exact rational
  representation and threshold outcome relation, separately from
  `above_probe.multiple`. A larger-multiple probe is not a break-even threshold.
  Every held assumption and the mathematical domain remain in the conclusion
  audit. An already-satisfied domain minimum is not necessarily a zero-return
  equality. Unattainable or unverified boundaries retain null thresholds even
  when a separate probe exists. No plausible multiple or DCF implication is
  inferred. The option must be boolean and cannot be enabled for a DCF objective.

For an operative objective conclusion, add the following after its terminal
section (index `0` in this example):

```json
{
  "kind": "objective_conclusion",
  "evidence_section": 0,
  "objective_id": "DCF_DISCOUNT_CLOSURE",
  "domain_scope": "SUPPLIED_ROWS",
  "research_judgment": {"stance": "undetermined"}
}
```

Set the plan's `objective_conclusion_required` to `true` to require a typed
conclusion referencing every terminal section. Missing, later, nonterminal or
wrong references fail; there must be at least one terminal section. Unsupported
objectives, universal domains, custom comparison targets/operators, caller proof
flags and authored AND/OR necessity claims are rejected. This bounded interface
does not prove arbitrary conditions; use a separately defined objective/domain
and the existing scenario-claims contract for such investigations. Multiple
conclusions can refer to one terminal section when different questions are being
distinguished. Existing plans without this option retain their original behavior.

This required-conclusion mode is **not** a strict whole-report semantic mode.
It ensures a replayed objective-specific conclusion is present and cannot switch
the computed comparator or scope. Separate arbitrary commentary can still
contradict it. That commentary remains visible and `PARTIAL_UNAUDITED_PROSE`;
independent review must assess the entire answer. A correct generated conclusion
does not excuse an unsupported central statement elsewhere in the same response.

The original raw plan, full manifest and every original source are retained,
along with complete producer/workflow artifacts. Copies can be moved as a whole;
verification uses retained relative paths and the same installed implementation.
No stateful or live broker/host workflow is supported or repeated.

`receipt.json` contains `response_file: "first-response.md"`,
`final_response_sha256`, `plan_sha256`, `manifest_sha256`,
`implementation_sha256` (installed Python file hashes), `context_sha256`,
`audit_sha256` and the complete artifact inventory. Its status is
`FINAL_REPORT_REPLAY_AND_BYTES_MATCH`, or `PARTIAL_UNAUDITED_PROSE` when additional
prose is present. Each prose span has UTF-8 `start_byte`, `end_byte` and `sha256`
under `unverified_spans`. Additional prose is visibly separated and never
certified, even if contradictory text passes byte comparison.

`whole_report_semantic_pass`, `source_authenticity_verified`,
`request_completeness_verified` and `execution_authorized` remain false.
Replaying an incomplete producer result does not make it complete. The original
plan can omit a relevant task entirely; this compositor does not infer intent,
prove source truth, establish complete task coverage or prevent an external
model from choosing a different response. A neutral capture control can check
receipt/file association; it cannot turn this receipt into a correctness grade.

Limits are eight sections, 16MiB per input/result file, 128MiB original corpus,
10,000 source files, 1MiB final response and 128KiB additional prose. Source
bridge sections retain their own complete corpus copies. Linked/reparse paths
and unsafe source names are rejected. Local hash receipts are consistency
evidence, not tamper-proof attestations against rewriting all artifacts.

Python API: `compose(plan_path, output_dir, manifest_path,
expected_manifest_sha256, source_root=None)` and read-only
`verify(directory, final_response_path=None, structured_analysis_path=None,
expected_output_contract=None)`.
Optional APIs are `prepare` with the same arguments as `compose`, and
`finalize(directory, expected_preparation_sha256)`. The preparation receipt binds
the complete retained preparation inventory and the replayed prospective output
hashes; it is local consistency evidence, not an attestation against fabrication
of all local files or proof that a plan covers the user's entire request.

## Generated structured research

For supported research that must deliver generated analytical statements only,
set `output_contract: "STRUCTURED_RESEARCH_ONLY"` in the plan. This rejects
`unverified_prose` and caller accounting `label` overrides; the accounting label
comes from the replayed producer. Unknown section/plan keys remain errors.
Legacy plans without this contract retain `LEGACY_UNAUDITED_COMPATIBILITY` and
their explicit unaudited-prose limits. Strict means a closed output schema and
replay, not semantic truth, investment correctness or complete request coverage.

An `issuer_facts` section has exactly `kind` and `request`. Its request is the
[issuer evidence](issuer-evidence.md) request, such as
`{"issuer_record":{"source_id":"primary","pointer":"/issuers/0"}}`.
It executes the supported source producer and retains every result field,
including original facts, topic coverage, unknown dates, covenant limitations
and unavailable objectives. It cannot accept caller-authored financial values.

Every composition now creates `analysis.json` from the same replay that renders
`first-response.md`. Its ordered `sections` contain fixed section indices/kinds,
producer identities, original requests, evidence audits and complete replayed
results. Sections are never flattened into a caller-selected metric dictionary.
Accounting `classification`, `eps`, `pe`, diagnostic ratio, original bindings and
unknowns stay distinct. An old scratch calculation can remain evidence without
becoming a current analytical assertion. Source quotations and original requests
retain their attributed/input roles; their presence is not semantic endorsement.

The report receipt adds `analysis_file: "analysis.json"`, `analysis_sha256` and
`output_contract`. Its full artifact inventory covers structured and readable
outputs. Verification rederives both, rejecting edited or omitted sections and
extra metrics even if a caller recomputes inventory hashes. The package version
and its exact bytes are also bound. `--structured-analysis FILE` checks a saved
copy; `--require-output-contract STRUCTURED_RESEARCH_ONLY` prevents downgrade to
a legacy partial report.

## Export one canonical response

```console
python -B scripts/final_report.py response REPORT_DIRECTORY --metadata metadata.json --output NEW_RESPONSE_DIRECTORY
python -B scripts/final_report.py verify-response NEW_RESPONSE_DIRECTORY --published-response response.json
```

The integrated entry point is `research_workflow.py final-response REPORT_DIRECTORY
--response-metadata metadata.json --private-output-dir NEW_RESPONSE_DIRECTORY`,
then `research_workflow.py final-response-verify NEW_RESPONSE_DIRECTORY
--final-response response.json`.

Metadata requires only `case_id` (an opaque declared identifier) and
`runtime_model_metadata` with `model` and `effort`; use `unknown` when unavailable.
Runtime metadata optionally accepts `python` and `model_identity_status`:
`UNKNOWN`, `PARTICIPANT_REPORTED` or `HOST_EXPOSED`. These remain declarations,
not verified model identity. The only other metadata keys are:

- `execution_limitations`: up to32 objects with `code` and optional bounded
  `detail`. Codes are `MEMORY_CONTEXT_AVAILABLE`, `MODEL_IDENTITY_UNEXPOSED`,
  `CAPTURE_INCOMPLETE`, `RUNTIME_DIFFERENCE`, `OTHER_UNVERIFIED_ENVIRONMENT`.
  Details remain visibly unverified environmental declarations, not analysis.
- `evidence_paths`: up to256 distinct relative `path`/`sha256` pairs. These are
  unverified external references, not imported data or current computed facts.

Unknown keys, manual `rows`, metrics, verdicts, status, input hashes and version
overrides are rejected. Export derives `candidate_version` and complete
`input_hashes`; `rows` is exactly canonical analysis sections and `limitations`
is the canonical typed limitation list. A second analytical dictionary is not
accepted. Extra financial work needs a supported producer/section or must remain
explicitly outside the generated analytical result; do not handfill missing rows.

Export requires the strict contract. It creates a new directory containing
`original-metadata.json`, a complete portable `report/` tree, `response.json` and
`receipt.json`. The envelope receipt has method `final-response-envelope-1`,
status `COMPLETED_CANONICAL_RESPONSE_EXPORT`, `response_file: "response.json"`,
`response_sha256`, `first_response_sha256`, `analysis_sha256`,
`report_receipt_sha256`, `metadata_sha256`, the strict output contract and full
artifact inventory. `response.json.artifact_association` links the same report,
analysis and receipt. Copies verify after relocation with the same implementation.

Python APIs are `export_response(report_directory, metadata_path, output_directory)`
and `verify_response(directory, published_response_path=None)`. Verification
replays the retained report before regenerating the envelope exactly; hashes of
an invented response cannot substitute for projection. Failures retain partial
files, never overwrite an existing output, and never upgrade unknown producer
results. Structured outputs are bounded to16MiB each. All semantic/authenticity/
request-completeness/authorization flags remain false.

A neutral capture control may bind both final files to these receipts. Such byte
association does not itself replay calculations or establish an independent
correctness grade. Review the actual requested coverage and source assumptions.
