# Source-bound research and reporting

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

`report.md` contains bindings, assumptions, unused fields, requested-work coverage,
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
