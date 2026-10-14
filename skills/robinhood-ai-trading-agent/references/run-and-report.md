# Run calculations and retain their reports

For a complete supplied-data analysis, start with the
[source-bound workflow](source-bound-workflow.md). It composes these adapters,
retains source selections and checks declared task coverage and result claims.
The individual commands below remain available for an already bound request.

Use these offline helpers when the requested calculation or evidence review has a
supported explicit input contract. They connect existing calculations to retained
facts, reducing opportunities to copy the wrong parameters or reconstruct results
in prose. They do not interpret an arbitrary prompt, authenticate observations,
validate an entire answer or control execution.

Choose a fresh local output directory outside the installed skill folder, with
an existing parent directory. "Private" means caller-selected access-controlled
storage; these exports do not encrypt files or establish Windows access controls.

Select the operation and source fields from the current request before running.
Use [research alignment](research-alignment.md) for the implemented request/evidence
receipts and calculation routing across cash, financial, strategy and horizon work.
Record conflicts between the request, examples and unrelated scenarios. A hash
can establish which bytes were used; it cannot establish that the chosen source
was the one the user intended. Do not silently substitute a nearby supported
strategy for an unsupported one. For example, a dual moving-average crossover is
different from price crossing a single moving average.

## Quant calculations

```text
python scripts/quant_report.py run REQUEST.json --private-output-dir NEW_PRIVATE_DIRECTORY
python scripts/quant_report.py verify NEW_PRIVATE_DIRECTORY
```

The request uses the [workbench contract](quant-workbench.md). Each job has an
explicit allowlisted operation and either `inputs` or an `inputs_source` object:

```json
{
  "id": "declared-hac",
  "operation": "validation.hac",
  "inputs_source": {
    "path": "measurements.json",
    "sha256": "REPLACE_WITH_EXACT_FILE_SHA256",
    "pointer": "/hac_inputs"
  }
}
```

The selected pointer must identify the complete named-argument object. Paths are
local and relative to the request file unless absolute. The referenced object is
copied without overrides. To evaluate a different scenario, declare a separate
input and retain its relationship to the source; do not edit a frozen source.
Only the installed helper's optional defaults fill omitted parameters. Missing
required inputs remain non-computations; they are not inferred from another job.

The new directory contains exact request/source bytes, prepared inputs, parameter
bindings, `bundle.json`, `facts.json`, `analysis.json`, `report.md` and a receipt.
An outer `COMPUTED` records that a helper ran. Its result can still describe an
infeasible allocation, ambiguous cash flows or insufficient evidence. Preserve
both levels when explaining results. A partial campaign retains successful and
unsuccessful jobs rather than pretending all calculations succeeded.

Verification reconstructs the inputs from retained bytes, checks artifact hashes,
replays the installed numerical implementation, and regenerates the facts/report.
Numeric replay uses the workbench's absolute tolerance `1e-8` and relative
tolerance `1e-7`; canonical report regeneration is checked byte for byte.
It does not establish source authenticity, appropriate operation selection or
agreement with prose outside these artifacts. Keep the matching skill and runtime
for replay; implementation changes can invalidate a previous receipt. See
[report facts](report-facts.md) for supported units, unknown metadata and optional
source-text export. Private files can contain supplied sensitive information.

## Analyst evidence

```text
python scripts/analyst_report.py REQUEST.json SOURCE_ROOT --private-output NEW_PRIVATE_DIRECTORY
```

This runs the existing [analyst evidence](analyst-research.md) helper. It accepts
its ordinary single-cohort request or an envelope:

```json
{
  "cohorts": [
    {"cohort_id": "one-year-usd", "request": {}}
  ],
  "supplemental_evidence": [
    {"kind": "historical_range", "record": {}}
  ]
}
```

Replace the empty example objects with actual supported records. Cohorts run
independently. Issuer, horizon, currency and share-price basis belong to each
request; do not pool incompatible records. The helper keeps admissible individual
targets, exclusions, provider consensus pools and provider-reported analyst track
records separate. Supplemental kinds are `fair_value`, `historical_range`,
`source_discovery` and `information_coverage`; they never enter target arithmetic.

`bundle.json` retains requests, helper results, source metadata and pointer-bound
facts; `report.md` renders those facts. Fact pointers resolve inside the bundle's
`artifact` object, whose canonical JSON hash is recorded. Preserve the original
request and referenced evidence files alongside the output for later replay.
The adapter executes supplied records, not independent extraction or acquisition.
Local evidence consistency does not prove the publisher, extraction or analyst
attribution is authentic. Different provider pools remain unreconciled unless
their actual constituents and methods explain the difference. Provider-reported
success rates do not establish causal investment skill or justify invented weights.

## Handoff preservation

The optional `handoff_report.py` receipt binds a declared local source file and
JSON pointer to the existing native-host handoff. It can compare a second supplied
payload and report structural/value differences without changing the original.
Use its `--help` for required hashes and output arguments. It is useful for finding
dollars-versus-shares, order-type or time-in-force substitutions.

```text
python scripts/handoff_report.py --source REQUESTS.json --expected-sha256 SHA256 --pointer /requested_order --private-output-dir NEW_PRIVATE_DIRECTORY
```

Optional comparison arguments are `--comparison`, `--comparison-sha256`,
`--comparison-pointer` and `--comparison-role proposed` (or `observed`). The
private directory retains exact source bytes and `receipt.json`; the command's
displayed summary omits private payload values and pointer paths.

The receipt is advisory and private. It neither submits an order nor authorizes,
refuses or delays native execution. Differences are observations, not gates.
Selecting the wrong pointer can still preserve the wrong request perfectly;
review the selected source against actual user intent. A matching payload proves
neither account balance correctness nor submission, broker acceptance or fill.

## Scope of comparisons

Report helper invocation, artifact completeness, numerical replay and narrative
agreement separately. A working adapter does not retroactively repair an old
answer. Evaluate new model responses independently on frozen inputs and unseen
variations, preserving prior results. Missing acquisition and unsupported custom
models still need separate work; do not assign them a pass from helper tests.
