# Checked answers across model hosts

Use the same workflow for Codex, Muse, Claude and other hosts. These tools run
inside the standalone skill with local files. They require no backend, daemon,
API subscription, broker connection or model-specific service.

## Run an explicit request once

For an existing workbench request, prefer the single offline entry point:

```console
python scripts/research_workflow.py execute REQUEST.json --request-role "Original supplied research request" --private-output-dir NEW_DIRECTORY
```

The directory must be new and outside the installed skill. The command preserves
the request and performs preparation, execution, verification and summary using
the existing source-bound workflow. Keep its completion record, answer facts and
export inventory with the run. Failure is retained evidence, not permission to
replace an available helper with model-written arithmetic. Inspect the concrete
error; report unavailable work honestly. Do not install dependencies or change
models without the user's authorization. For other input layouts, first bind the
original source records as described in [source-bound-workflow.md](source-bound-workflow.md).

The generated report distinguishes execution, verification and requested-work
coverage. A successful command or verified file does not establish complete
coverage, correct source interpretation, source authenticity or investment merit.
Retain failed jobs and nested unresolved results alongside successful jobs.

## Preserve numerical meaning when writing

Use `answer-facts.json` and `answer-facts.txt` for the supported numerical fields.
Their labels are fixed by operation and result field, with scenario, unit and
pointer retained together. In particular:

- Sale costs and sale net proceeds are separate facts.
- Per-share cost rates and aggregate currency costs are separate facts.
- A selected order and the maximum affordable order are separate scenarios.
- A null return remains unresolved; outer computation success is not a return.

Keep those generated meanings when shortening the answer. Unsupported fields
remain explicitly unrendered; use the complete verified report and typed
comparisons to assess them. Do not rename a field to fit a preferred conclusion.
The summary does not certify arbitrary prose. Review qualitative and conditional
claims separately under [evidence-semantics.md](evidence-semantics.md#final-claims-and-scenario-review).

## Concentration and incomplete accounts

Read the typed concentration evidence accompanying source alternatives. Dollar
exposure, a fraction of known equities, and a full-account concentration are
different quantities. Use a ratio's bound status only with its recorded numerator,
denominator, completeness and assumptions. Unknown unclassified assets can affect
both numerator and denominator. They do not automatically make the observed ratio
a lower bound. If a bound is not justified, describe a sensitivity or unknown
concentration instead. Do not extend a bound on dollars to a bound on a percentage.

## Identity and provenance

Run `scripts/research_preflight.py` for package diagnosis. `VERSION`, the package
manifest and the active package-version label in `SKILL.md` must agree. Treat
versions inside historical inputs as historical provenance, never as the current
loaded package. Record the actual package path and runtime used.

Use the scope-aware comparator for hash claims:

```console
python scripts/evidence_provenance.py HASH_COMPARISON.json
```

```json
{
  "operation": "compare_hashes",
  "left": {"algorithm": "sha256", "canonicalization": "raw-bytes", "scope": "original-request", "digest": "[ACTUAL_SHA256]"},
  "right": {"algorithm": "sha256", "canonicalization": "raw-bytes", "scope": "original-request", "digest": "[ACTUAL_SHA256]"}
}
```

Supply actual digests and the precise object/projection being compared. Different
scope, canonicalization or algorithms mean not comparable; missing metadata is
unknown. Equal-looking hashes from different scopes do not establish equal inputs.
A contract hash does not cover every job unless that is its actual defined scope.

The same CLI accepts `operation: classify_evidence` and a `record` with `origin`
(`retained` or `current`), `kind` (`synthetic_record`, `invocation` or `replay`), and
observed boolean fields `execution_observed`, `artifacts_available`,
`verification_passed`. This classifies explicit declarations, not authenticated
execution. Never set them true from a filename, prose assertion or synthetic
historical invocation. The runner's completion record reports its actual local
work; host upload, download and collection remain separately observed events.

## Export and comparisons

A local export inventory proves only which files were inventoried locally.
Attach available reports when useful and record collection separately. A host
that fails to expose or download an artifact has an export limitation; do not
claim the receiving reviewer acquired or replayed that file.

Use fresh participant contexts, identical frozen input-only packets and candidate
versions for comparisons. Preserve each first response and failure. Compare core
calculations, explanatory errors, requested-work coverage, execution and artifact
collection separately. A correct manual result is not proof the required workflow
ran. A skipped participant is not agreement. These tools reduce avoidable variation
without guaranteeing that every model follows the workflow or makes identical
future judgments.
