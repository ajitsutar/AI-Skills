# Complete registered attempts and forward captures

`scripts/experiment_registry.py` retains a campaign's registered contracts,
failed and abandoned attempts, constraint revisions, prompt bytes, model context,
data vintages and actual result/error bytes. This is research evidence, never an
execution gate or a claim that a strategy is profitable.

For a requested local sequence, execute each mutation once in the supplied order,
then audit read-only. Draft the result from the retained return values, errors,
and journal transitions. Do not write an immutable answer predicting which
operations will succeed before executing the sequence. A rejected call does not
establish a recorded result or consume a result slot; inspect the actual journal
before interpreting a later call. Keep a preliminary plan separate from the
first delivered result. Preserve failed calls even when a later call succeeds.

Create a new private directory outside the installed package. Register each
attempt before running it. Record every result, including failures; a changed
constraint, universe, prompt or selected method is a new attempt referring to its
parent and a revision reason. Do not overwrite a losing attempt with a winner.

```text
python scripts/experiment_registry.py PRIVATE_REGISTRY register CONTRACT.json PROMPT.txt
python scripts/experiment_registry.py PRIVATE_REGISTRY result trial-1 failed ERROR.txt
python scripts/experiment_registry.py PRIVATE_REGISTRY audit
```

The contract schema is demonstrated in
`examples/experiment-attempt.json`. It records model host/name/version/settings,
package/runtime/universe hashes, data-vintage IDs/hashes/availability times,
constraints, selection rule, training/evaluation/label-end windows and embargo.
These timestamps and hashes are declarations except for the prompt and captured
artifact bytes, which the registry actually reads and hashes. Merely declaring a
vintage time does not establish historical publication availability.

Every `data_vintages` entry is a declared preselection input. Validation flags
entries whose availability is later than evaluation start; it does not silently
shift the start date or manufacture a publication timestamp. Streaming information
and outcomes belong in separately timestamped captures, not future-known bytes
misrepresented as frozen preselection inputs.

Audit explicitly distinguishes development, late registration, future inputs and
registered-window overlap. A timely holdout/forward contract with no detected
overlap is only `LOCALLY_PROSPECTIVE_CONTRACT_ONLY`. Even that state never proves
a globally untouched holdout: prior unregistered searches, clock manipulation,
model training knowledge and external selection remain outside this journal.
Late historical holdout registration is retained for transparency, not rejected
and erased or promoted into evidence of precommitment.

The journal has a hash chain and immutable content-addressed artifact copies.
An atomic writer lock prevents concurrent mutations; an existing lock fails fast
and must be reconciled against its owner rather than silently stolen. Missing or
edited retained blobs fail audit. Root paths are explicit, artifact input is
bounded to 50 MiB, and the API never downloads or executes a supplied file.
Keep credentials, private routing and unnecessary personal information out.

`validate_attempt(document)` and `overlap_review(document)` are pure functions
suitable for a numerical workbench. The latter reports overlapping evaluation
and label windows and cross-trial training contamination. It includes failed
trials in the registered count, but does not calculate a multiple-testing penalty
or discover trials that were omitted. Use the statistical validation helpers with
the complete retained search inventory; dependent trials require appropriate
assumptions, not just a nominal count.

## Forward paper evidence

Use purpose `forward_paper` and register before the evaluation window begins.
Capture each frozen prediction after its declared decision time and strictly
before its target time; duplicate decision captures and completed attempts are
rejected. Both timestamps must fall inside the registered evaluation window.

```text
python scripts/experiment_registry.py PRIVATE_REGISTRY forward trial-1 DECISION_ISO TARGET_ISO PREDICTION.json
```

Capture files contain the actual forecast/weights, source cutoff, available data,
intended execution convention and any unknowns. At the end, retain a separate
outcome/reconciliation artifact through `result`. This ledger does not create
orders, calculate paper fills, or transform forecast files into observed trading
performance. Use the applicable accounting engine for outcomes and retain costs,
corporate actions and differences between forecast and actual execution.

The machine clock is not independently notarized. The filesystem owner can
replace an entire journal and recompute its hashes; a hash chain is not proof of
authentic timestamps or a complete experiment history. Preserve external signed
or archived evidence separately when that assurance is required. Stateful
registration/capture/result calls must not be rerun by a pure numerical replay
verifier; call their CLI/API once, then audit retained evidence read-only.

Schema 2 requires explicit accounting, benchmark, cash, dividends and costs descriptions in `conventions`. Complete outcomes require actual result, accounting and benchmark files: `result ATTEMPT complete result.json --accounting accounting.csv --benchmark benchmark.csv`. Failed/abandoned outcomes retain the actual error without invented accounting. Non-performance experiments must retain explicit not-applicable accounting/benchmark statements, rather than fabricated returns. All bytes are copied and hashchecked; later source edits cannot revise a recorded result. Correct accounting is not inferred from binding bytes. A changed convention requires a new linked attempt.
