# Source-bound research and reporting

## Complete original-object briefings

For a structured request without `requested_categories`, use `request_coverage.py`
in `ORIGINAL_OBJECTS` mode. Deliver source-specific authored meaning beside
optional verified native reports. Completing every numerical job does not answer
remaining contextual questions; retained source bytes and generic disclaimers
do not replace the requested analysis.

Use the same `compose`/`verify` commands and optional metadata described below.
An object plan has this shape (member names are illustrative):

```json
{
  "kind": "ORIGINAL_OBJECTS",
  "request_ref": {"source_id": "original-request", "pointer": ""},
  "contexts": [
    {"id": "supporting-notes", "link_pointer": "/supporting_file", "source_id": "original-notes"}
  ],
  "rows": [
    {
      "source_ref": {"source_id": "original-notes", "pointer": "/maintenance"},
      "disposition": "AUTHORED_ANALYSIS",
      "meaning": "Explain what this entire retained member establishes for the requested purpose, and what it does not establish.",
      "limitations": ["State a source-specific remaining limitation or explain why none was identified."],
      "evidence_refs": [],
      "supporting_annex_ids": []
    }
  ]
}
```

This abbreviated example is not complete: supply exactly one row for every
top-level member of the original request and every linked context object, up to
128 distinct members. Bind the request at its root, not a convenient subobject.
Each row selects the entire member; nested values, null, false, zero and arrays
remain intact. JSON Pointer escapes are `~0` for `~` and `~1` for `/`. Output
follows original source member order.

Object mode retains original JSON number tokens exactly in every request, context,
member and evidence binding, including tiny/large exponents, long fractions,
integers and signed zero. Numbers remain JSON numbers; numeric-looking strings,
booleans and null stay distinct. Source strings use normal JSON escaping; original
whitespace, string escape spelling and object key order may normalize. Decode the
output with a lossless-number reader when precision matters: a consumer's default
binary-float decoder can still round an otherwise exact JSON token. Original file
bytes and hashes remain retained separately. Unsupported values, depth beyond64
or an encoded object above16MiB reject delivery rather than changing or truncating
values. Existing category output and native annex encodings are unchanged.

Required contexts are direct top-level request string values resolving to pinned
JSON-object sources, relative to the original request file. The `contexts` list
must match every such link; IDs are display labels. Missing relative `.json`
sources, unsafe local paths, substituted source IDs, omitted/duplicate links and
partial member rows reject delivery. Multiple links to one source retain every
link and cover its members once. URLs are never fetched. JSON-array links remain
request members rather than context objects; arrays and nested links are not
recursively expanded. This bounded mode does not infer exhaustive requirements
from prose or discover additional files.

Each member requires nonempty authored `meaning`, at least one nonempty
`limitations` entry and a disposition: `AUTHORED_ANALYSIS`, `SUPPORTED_ANNEX` or
`NON_ANALYTICAL_CONTEXT`. The latter needs a meaningful relevance rationale; it
is not permission to skip a requested conclusion. `SUPPORTED_ANNEX` requires a
checked annex reference, while its relevance remains unverified. Optional
`evidence_refs` bind additional exact original JSON values. A nested member's
meaning and the natural-language request still require substantive review.

Authored meaning, dispositions and annex associations remain
`SEMANTICALLY_UNVERIFIED`; populated rows do not prove analytical completeness.
No financial calculation, source authentication or correctness grading occurs.
Use readiness tools only when their original input contracts are supported; do
not invent calendars, clocks or identity evidence to satisfy a schema. Deliver
unsupported source-fitness conclusions as attributed judgments with their limits.

The full authored answer has its own first-response hash and association. Optional
native annexes retain unchanged strict verification and complete artifact trees.
For comparison protocols, use the applicable outside-compositor path for the
complete answer. Never associate an annex hash with the larger answer or append
authored text to a strict canonical response. Controls remain unchanged.

## Complete category briefings

`request_coverage.py` preserves a supplied machine-readable request's complete
`requested_categories` inventory when a briefing includes work outside existing
report producers. It assembles the **authored** briefing/source-plan rows and
optional checked annex references into its own `first-response.md` and
`response.json`. Category presence is checked; analytical correctness and semantic
completeness are not. Continue using independent review to decide whether the
actual category analysis, useful source routes and requested conclusions are sound.

```console
python -B scripts/request_coverage.py compose delivery-plan.json --manifest SOURCE-INGRESS.json --manifest-sha256 EXTERNAL_PIN --source-root ORIGINAL_ROOT --output NEW_DELIVERY
python -B scripts/request_coverage.py verify NEW_DELIVERY --first-response SAVED_FIRST_RESPONSE.md --response SAVED_RESPONSE.json
```

For a comparison protocol that requires an explicit case/model envelope, add
`--metadata metadata.json` to compose. The file uses the existing
`final_report.response_metadata` schema: `case_id`, `runtime_model_metadata`
with `model`/`effort`, and optional `evidence_paths`/`execution_limitations`.
These are retained unverified declarations, not analytical overrides. Without
metadata, the declared ID is `unspecified` and model/effort are `unknown`; provide
the actual task ID when the protocol requires it. The adapter derives
`candidate_version` from the installed package and `input_hashes` from every
original manifest source. Metadata references to separately captured calculations
are not imported or replayed by this helper.

The output directory must be new. The original plan/corpus, failures and optional
annexes are retained; nothing is overwritten or deleted. Verification is read-only.
The complete source inventory is checked against the external pin. This command
does not discover, browse or acquire sources, run financial calculations, request
credentials or change accounts.

The plan selects the whole original request object and its original fields:

```json
{
  "request_ref": {"source_id": "original-request", "pointer": ""},
  "categories_pointer": "/requested_categories",
  "source_scope_pointer": "/source_scope",
  "constraints_pointer": "/session_rules",
  "rows": [
    {
      "category": "maintenance",
      "observations": [
        {
          "source_ref": {"source_id": "retained-record", "pointer": "/observation"},
          "interpretation": "An authored interpretation limited to the retained record's declared scope."
        }
      ],
      "analysis": "The category briefing, including unsupported conclusions and their limits.",
      "free_source_plan": {
        "routes": [
          {
            "source_kind": "Original public documentation",
            "purpose": "Resolve the identified coverage question.",
            "stopping_condition": "Stop after the original documentation and one relevant independent source.",
            "execution_status": "NOT_EXECUTED"
          }
        ],
        "no_route_reason": null
      },
      "optional_access": {
        "assessment": "Describe actual retained access, or state that it is unknown.",
        "improvement_or_no_need_reason": "Explain the useful field, freshness or history improvement, or why none is needed.",
        "source_refs": []
      },
      "remaining_gaps": ["State the remaining feature or source gap."],
      "supporting_annex_ids": []
    }
  ]
}
```

There must be exactly one row for every category in the **original** array, up to
32 categories. The example's category is illustrative; do not replace a larger
original array with it. Literal replacement inventories, alternate subset pointers,
missing/duplicate categories and unrequested rows are rejected. Output rows follow
original category order. Unknown category names remain required and visible.

`categories_pointer` is fixed to `/requested_categories` in this bounded schema.
The scope string and constraint object are selected relative to the original
request object. If it contains `source_scope` or `session_rules`, the corresponding
pointer must select that exact field, preventing redirection to convenient
alternative text or permissions. Other schema pointers remain declared selections;
the entire original request is retained for review. No permission is inferred from
the selected constraints. Free-text requests without this inventory require an
outside-compositor answer or a separately reviewed scope extraction; this helper
does not infer exhaustive requirements from prose.

`observations` may be empty when there is no retained evidence; explain the gap.
Each nonempty observation binds an original JSON value and preserves the source
hash. Source content remains attributed and unauthenticated. `interpretation`,
`analysis`, access assessment, improvement reasoning and gaps are authored and
explicitly `SEMANTICALLY_UNVERIFIED`, even when every category row exists. A
structurally valid but irrelevant answer is still a substantive failure.

All prospective route records must say `NOT_EXECUTED`. If no route is appropriate,
use an empty `routes` list and a substantive `no_route_reason`, preserving offline
and source-exclusive scope. Access references bind retained JSON receipts; their
meaning is not automatically authenticated or a purchase requirement.

Optional `annexes` accepts only existing supported strict report directories:

```json
{
  "id": "checked-analysis",
  "kind": "final_report",
  "directory": "checked-report",
  "receipt_sha256": "EXACT_RETAINED_RECEIPT_SHA256",
  "first_response_sha256": "EXACT_RETAINED_ANNEX_FIRST_RESPONSE_SHA256"
}
```

Use this object inside an `annexes` array. Paths are relative to the delivery
plan's directory and cannot escape it. `kind: "canonical_response"` instead
selects a `final_report.py response` export and additionally requires its
`response_sha256`. Each annex is verified with its native verifier, copied by exact
inventory into `annexes/ID`, and replayed there. A row may name its IDs in
`supporting_annex_ids`. No arbitrary file tree or plugin is imported. Direct
captured calculation/parser evidence remains valid outside this optional annex
mechanism; keep it in the task's normal evidence record and cite it in the authored
analysis without implying that this adapter replayed it.

The full answer has method/association `request-coverage-delivery-1`, not the
strict compositor's canonical-response identity. Preserve actual complete-answer
bytes under normal capture/seal controls. Do not use an annex's first-response
hash for the larger briefing, relabel the annex as the whole answer, or modify
frozen controls. `STRUCTURAL_SCOPE_AND_BYTES_CHECKED` is neither a correctness pass
nor permission to mark research complete. A failure retains an explicit diagnostic
with the missing scope; finish that work rather than hiding it in a partial annex.

The existing research workflow's `coverage(requirements, jobs)` remains useful for
declared job execution. It does not establish that its caller-declared requirements
exhaust the original request. Use the original-bound category inventory for this
briefing route and assess semantic completeness separately.

For original-corpus analyst targets and REIT comparisons, use
[integrated source research](supplied-research.md) through `research_workflow.py source-run`.
It connects source derivation/binding to computation, generated reporting and
saved-byte replay. Its `source-verify` command replays the retained originals.
Unbound declared REIT arithmetic remains conditional; a prepared caller-created
input object alone cannot certify original accounting basis.

For supplied-data numerical research, use `research_workflow.py` as the entrypoint.
It calls the installed calculations, request/evidence receipts and report-facts
adapter, producing the result and its report together. Reimplementing an available
operation in an ad hoc script loses those bindings and checks.

When the original record fits a documented source-aware operation, bind that
whole record instead of transcribing selected fields into lower-level arguments.
Portfolio source roles, dated projections/alternatives and settlement sweeps
preserve supplied flows and unknown bases. Recommendation context joins original
security rows to computed allocations. Financial observation pointer bindings
retain missing precision; typed price comparisons retain exact denominator
meaning. Their contracts are listed in [the workbench catalog](quant-workbench.md).
Use explicit mappings for other schemas and inspect every material omitted field.

```text
python scripts/research_workflow.py schema
python scripts/research_workflow.py run PLAN.json --private-output-dir NEW_DIRECTORY
python scripts/research_workflow.py verify NEW_DIRECTORY
python scripts/research_workflow.py summary NEW_DIRECTORY
```

For a complete explicit request, `execute REQUEST.json --request-role "Original supplied request" --private-output-dir NEW_DIRECTORY` runs preparation, execution, verification and answer-fact projection together. Preserve its completion and export records, including failures. See [checked answers across hosts](model-alignment-hardening.md).

For large or repeated portfolio jobs, add `--compact-evidence` to `run` or
`execute`. It retains complete sources/results in a verified gzip object store,
deduplicates identical artifacts and avoids repeating full leaf-fact tables in
every report. Claims and numerical replay stay unchanged; leaf facts are available
on demand. Read [compact evidence](compact-evidence.md) for logical-path readers,
resource limits and the distinction between a locator and a materialized fact.


The runner is offline. Obtain authorized current data separately and save its
actual bytes and acquisition times before binding files. For an offline request,
missing source bytes remain missing; do not run acquisition commands. The runner
has no network, broker or scheduling interface.

## Prepare an existing explicit request

When the workbench request already contains the original full `inputs` objects,
avoid reconstructing their fields as a new plan. Prepare directly from that file:

```text
python scripts/research_workflow.py prepare REQUEST.json --request-role "Caller-supplied research request" --private-output-dir NEW_PLAN_DIRECTORY
python scripts/research_workflow.py run NEW_PLAN_DIRECTORY/plan.json --private-output-dir NEW_RUN_DIRECTORY
python scripts/research_workflow.py summary NEW_RUN_DIRECTORY
```

`prepare` retains the original request bytes, hashes them, and selects each whole
input object at `/jobs/INDEX/inputs`. It copies the contract, job IDs, operations,
requirements and claims exactly. Supplied parameters are unchanged; omitted
optional parameters remain omitted until the installed helper binds its defaults
during `run`. Invalid helper parameters remain invalid and are reported by that
helper. No operation, role, parameter, requirement or claim is inferred from prose.

The accepted request has `schema_version: 1`, `contract`, and nonempty `jobs`, plus
optional `network_mode: "offline"`, `requirements` and `claims`. Each job has exactly
`id`, an installed workbench `operation`, and either `inputs` or `inputs_source`.
Unknown wrapper fields and overrides are rejected rather than silently discarded.
Existing `quant_report.py` source selections are supported without rewriting data:

```json
{
  "id": "uncertainty",
  "operation": "validation.hac",
  "inputs_source": {
    "path": "observations.json",
    "sha256": "EXISTING_EXACT_FILE_SHA256",
    "pointer": "/uncertainty_inputs"
  }
}
```

For each distinct `inputs_source.path`, add one explicit role to the prepare
command, for example `--source-role observations.json "Caller-declared synthetic observations"`.
Paths are resolved relative to the original request unless absolute local paths
are supplied. The existing hash must match, and the pointer must select the entire
input object. Preparation copies the exact bytes to predictable local source
paths; subsequent runs use those retained copies. Missing, extra or duplicate
role declarations fail preparation. Roles describe the caller's declaration;
they do not authenticate observations.

Prepared plans re-derive their contract, jobs, bindings, requirements and claims
from the retained request before execution and replay. To revise the request,
prepare its revised bytes in a new directory. Neither preparation nor execution
overwrites an existing output directory. If the original request lacks requirements
or claims, they remain empty; missing checklist coverage remains diagnostic.
Manually composed plans remain available for contract/report operations and
explicit source/assumption compositions that are outside this preparation format.

## Plan structure

Use the current prompt and workbench contract fields. List requested subtasks as
`requirements` before selecting operations. Each requirement names its intended
operations; a software-document check cannot satisfy an issuer-release audit.
An unsupported task can have an empty job list and a reason, remaining unaddressed
rather than succeeding by omission. Review this checklist against the prompt.

Sources use unique IDs, relative paths under the plan directory, exact SHA-256,
`json`, `text` or `bytes` format, and a declared role. Every scalar argument is
selected with a JSON pointer or an explicit assumption with a reason. Objects and
arrays compose those selections. A pointer can select an entire object.

```json
{
  "schema_version": 1,
  "network_mode": "offline",
  "contract": {
    "prompt": "Evaluate the supplied forward-study observations",
    "purpose": "research",
    "base_currency": "USD",
    "horizon_id": "P6M",
    "as_of": "2026-10-13T16:00:00Z"
  },
  "sources": [{
    "id": "observations",
    "path": "observations.json",
    "sha256": "REPLACE_WITH_EXACT_FILE_SHA256",
    "format": "json",
    "role": "declared forward-study input"
  }],
  "jobs": [{
    "id": "admissibility",
    "operation": "validation.forward_observations",
    "arguments": {"document": {"$source": {"id": "observations", "pointer": ""}}}
  }],
  "requirements": [{
    "id": "forward-evidence",
    "question": "Which supplied rows count as forward observations?",
    "job_ids": ["admissibility"],
    "expected_operations": ["validation.forward_observations"]
  }],
  "claims": [{"id": "helper-result", "job_id": "admissibility", "pointer": "/result"}]
}
```

Replace the illustrative contract and source with the actual inputs. The selected
object must satisfy the helper's schema. Defaults come from the installed helper.
A chosen scenario instead uses
`{"$assumption": 0.01, "reason": "Analyst-proposed slippage scenario"}`.
Assumptions remain visible and do not become observed data.
For a derived financial observation, a formula written in an assumption reason is
not execution evidence. Bind the raw operands and use the supported calculation:
[fundamental ratios](fundamental-toolkit.md#derived-observed-inputs) can compute
midpoint balances and revenue-minus-gross-profit directly. Keep their derivation
output and source bindings, and reconcile intermediate and final narrative
numbers. Where no supported operation exists, retain the executed local
calculation and bind its output as a derived source rather than disguising it as
an observed value or forecast assumption. The workflow does not parse assumption
reasons or certify arithmetic described in prose.

Use `quant_workbench.py operations` and the calculation guide for exact arguments.
`ranking.route`, `ranking.replay` and `ranking.compare` bind retained profile
identity and distinguish numerical overlap from missing decision evidence; see
[ranking alignment](ranking-alignment.md).
Additional operations are `research.bind_request`, `research.inventory_evidence`,
`research.route_horizon`, `research.audit_ranking`, `report.quant` and
`report.public_vqm`. Contract operations take `document`. Report operations take
`source_id`, optional `custom_source_id` and `include_source_text`; bind identifiers
as declared selection assumptions. Reports preserve and verify the entire canonical
fact projection. Historical provenance remains historical, not current replay.

## Use the generated results in the answer

In ordinary mode, `report.md` contains bindings, assumptions, unused fields, requested-work coverage,
actual results and all supported facts. `COMPUTED` means an operation ran; nested
results may remain unresolved, infeasible or inadmissible. Read the nested status
and complete cash/scenario path, including deferred events.

`claims` project result pointers without recopying values. An optional `assertion`
checks a literal against the actual value, returning `MATCH`, `CONTRADICTED` or
`UNRESOLVED_POINTER`. Literal assertions require exact JSON values and types;
object key order is immaterial, but list order is preserved. Numerical replay
tolerances apply to recomputed quantitative results, not literal assertions.
Use the actual projected value when displaying rounded numbers. For inequalities or
metadata-sensitive comparisons, run `analysis.compare_claim` or
`evidence.operand_compatibility` and project that result. Preserve issuer, units,
denominator, share basis, period and evidence state in the explanation. An analyst
label is not validated simply because its selected pointer is consistent.

Use the generated facts as the numerical portion of the answer and attach the
retained report when useful. Separate business interpretation, proposed scenarios
and causal hypotheses. Unsupported custom analysis retains its own code/inputs
and cannot claim an installed operation or verification ran.

`summary DIRECTORY` first verifies the complete retained run, then writes a
deterministic JSON projection to stdout: exact declared claim values, coverage,
source identities and pointers, assumptions, unused source pointers, job statuses,
nested evidence states and literal null pointers. Keep captured values in the
private workspace. No number is rounded and no narrative meaning is added. Null
and nested-state pointers are relative to that job's result; each job also gives
its absolute pointer within `result.json`. Select narrow claims for concise numeric
answers, including any needed units, basis or evidence-state fields. The summary
does not invent semantics for a bare number, and it does not replace the complete
canonical report. It is projected afresh after verification, never reused from a
previous summary file.

Verification rebuilds source selections and calculations, checks retained inputs,
replays quant bundles and regenerates the report. It cannot authenticate sources,
validate omitted tasks or check arbitrary prose outside the report. It never
approves or blocks a trade. Preparation reduces copying and binding errors;
neither command guarantees that a model chooses the right request or follows the
workflow in a future answer.

## Interpretation boundaries

| Evidence | What it establishes | What remains separate |
|---|---|---|
| Exchange listing directory | Listings at that date | Named-index membership needs constituent evidence |
| Two missing fields | Both are unknown | Equality or agreement is unestablished |
| Review flag or classifier unavailable | That review/capability status | Final selection and per-name recommendation evidence |
| Borrow fee | Quoted fee under source terms | Inventory, availability, utilization and recall |
| Provider target averages | Reported provider statistics | Reconciliation needs constituents, vintages and methodology |
| Price and EPS | Arithmetic after identity/basis matching | Concurrent period changes cannot be attributed solely to a split |
| Fee-adjusted residual | An accounting residual | Causal attribution needs matched timing, fills, exposures and benchmarks |
| Similar strategy text | Textual similarity | Implementation, fills and admissible forward observations |
| Year/month-only event | An interval | Exact timing relative to exit may remain unresolved |
| Holdings plus cash | Identified assets | Reconcile declared equity; future grants are separate |
| Date-only cash availability | Calendar-day evidence | Ordering versus intraday withdrawals may be unknown |

Use [evidence semantics](evidence-semantics.md), [research alignment](research-alignment.md)
and operation-specific guides. Do not infer causality, settlement, day-close
holdings or a covenant definition from a convenient proxy.

Only hash completed artifacts. A command that is still writing a response has
unfinished stdout, stderr and command receipt; those are not valid fixed artifact
references inside that same response. Compose the response after substantive
commands finish. Its authoring command may be recorded separately afterward;
never claim a placeholder stream hash proves the completed stream. Preserve an
incorrect original reference as a disclosed evidence failure, not a silent repair.

For complete retained market tasks, use the [combined canonical source reports](final-report.md#complete-retained-market-workflows):
`market_sources_report` binds the original whole parser-job list, raw files and
explicit cutoff; `market_flow_report` binds the requested original views;
`institutional_report` adds pure native `brief` results. Missing interface schema
version may be constructed from the installed parser contract, while the cutoff
must come from original evidence. Never invent publication/availability clocks,
share bases or other market metadata to make parsing succeed. Keep native
rejected rows and unknowns visible. These supported outputs can share one exact
canonical response; broader authored work still follows the mixed briefing route.

The parser producer automatically includes the documented historical-descriptor
metadata profile from the whole JSON document bound by its existing `as_of_ref`.
This contributes source-specific historical-membership, availability and vintage
limitations to that same canonical response. It performs no acquisition or
historical study and never certifies point-in-time fitness or complete request
coverage. Inspect partial-audit bounds and unassessed fields. Exact original field
values use typed `original_json` JSON text to preserve numeric tokens; the native
parser results keep their established numeric conventions. Broader unsupported
context still needs authored analysis through the complete-object route. See
[metadata fitness](market-sources.md#automatic-bound-context-metadata-fitness).
