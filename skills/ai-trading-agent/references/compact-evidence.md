# Compact, replayable workflow evidence

Use `--compact-evidence` for large source-bound portfolio runs or repeated jobs.
It changes storage and presentation, not requested calculations, source fields,
claims, numerical tolerances or verification requirements. Legacy output remains
the default for callers that need physical `result.json` and full fact tables.

```text
python scripts/research_workflow.py execute REQUEST.json --request-role "Supplied research request" --compact-evidence --private-output-dir NEW_PRIVATE_ROOT
python scripts/research_workflow.py verify NEW_PRIVATE_ROOT/run
python scripts/research_workflow.py summary NEW_PRIVATE_ROOT/run
```

`run PLAN.json` and `quant_report.py run REQUEST.json` also accept this flag.
Verification detects the retained storage format; do not pass the flag to
`verify`. Existing `source-role`, source-hash and new-output-directory rules apply.
No download, installation or external action is performed by these commands.

## What stays complete

The run keeps exact source bytes, each complete bound argument object, prepared
inputs, native numerical bundles, results, claims, assumptions and the complete
unused-field inventory. Logical paths and JSON pointers retain their meanings.
`storage-index.json` maps each logical path to an immutable SHA-256 gzip object,
raw byte count and hash, and compressed byte count and hash. Identical artifact
bytes share one object within that run. Compression uses bounded writes and
deterministic gzip metadata. Index updates are atomic; an interrupted run remains
a partial checkpoint, not successful execution.

The verifier checks all indexed artifacts named by the workflow receipt, then
reconstructs source selections, replays numerical helpers, checks literal claims
and regenerates the canonical presentation. Compact mode does not reuse a prior
verification success marker instead of doing those checks. It has the same
source-truth, timestamp, selection and financial-interpretation limitations as
the ordinary workflow.

## Bounded presentation and on-demand facts

Ordinary per-job quant reports expand every input/result leaf into metadata-rich
fact rows. Repeating that table across a large multi-job workflow can cost much
more space and time than calculation. Compact mode stores a hash-bound
`COMPLETE_SOURCE_ON_DEMAND` descriptor in each ordinary quant job's `facts.json`.
It explicitly says leaf facts were **not materialized**. The complete native
`bundle.json` remains available; no source or result field was discarded.

The main compact report contains job status and exact artifact/pointer/hash
locators rather than repeating full argument arrays, results and per-leaf prose.
It displays at most 100 job summaries and a 32,768-character preview; the full job
list and all claims remain in `result.json`. Read narrow declared claims through
`summary`, or extract the exact result when detailed review is needed. A short
report does not establish that omitted presentation fields were reviewed.

Explicit `report.quant` / `report.public_vqm` jobs continue to compute their
requested complete canonical fact projections. Compact mode does not silently
change those operations' outputs or invalidate their fact-pointer claims.

Extract only the needed logical artifact into a new private file:

```text
python scripts/evidence_storage.py list NEW_PRIVATE_ROOT/run
python scripts/evidence_storage.py extract NEW_PRIVATE_ROOT/run result.json --private-output EXTRACTED_RESULT.json
python scripts/evidence_storage.py extract NEW_PRIVATE_ROOT/run jobs/0000/quant/bundle.json --private-output EXTRACTED_BUNDLE.json
python scripts/report_facts.py quant EXTRACTED_BUNDLE.json --private-output FULL_FACTS.json
```

The extraction checks both compressed and raw hashes before creating an exclusive
new output. `report_facts.materialize_compact(raw_bundle, descriptor)` also
validates the descriptor's exact source/options/code bindings before regenerating
the unchanged full adapter. Do not relabel the compact locator as a complete
materialized fact table. Host APIs that insist on ordinary files must explicitly
extract those files; no implicit expansion of the entire store is necessary.

## Resource and portability limits

This is bounded artifact storage, **not a streaming numerical engine**. JSON
sources, an individual input/result and helper arrays still must fit memory.
There is a 1 GiB uncompressed-object limit, a 16 MiB index limit and a 256 MiB
resident compressed-artifact limit; exceeding a limit fails explicitly rather
than dropping evidence. Gzip output is checked against declared sizes before and
during decompression. Readers reject path traversal, symlink/reparse ancestors,
changed bytes and oversized objects. These checks do not claim race-proof
security against another process modifying the filesystem concurrently.

Preparation and `execute` checkpoint/summary files remain ordinary files outside
the run store; the store deduplicates exact artifact bytes within the run, not
arbitrary matching subtrees or every file on a host. Historical bundles still
bind the code and source vintage under which they were created. Updating the
skill does not make an old run a current-code replay or alter frozen evidence.

Portable gzip needs only Python's standard library. This mode never depends on
Codex, Muse or Claude having a hidden cache and does not change the separate
explicit opt-in requirements for [partial fetching](partial-fetch.md).
