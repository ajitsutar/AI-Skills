# Bind report statements to retained helper evidence

Use this optional route when a report interprets scenario conditions, names an
accounting ratio, presents a latest-per-firm cohort, or distinguishes source
presence from an adapter binding. Correct calculations do
not ensure that a later sentence keeps the same objective, logical connective,
accounting basis or selected records. This route produces a narrow set of typed
statements and checks their placement in the actual saved response.

It is a report draft tool, not a general prose truth classifier. It never declares
`whole_report_semantic_pass`. Exact hashes prove byte consistency, not source
truth, correct original mapping, execution authenticity or complete user-request
coverage. A fully consistent hand-authored output still needs original-source
and execution review.

## Draft, audit, then retain the first response

1. Retain original inputs and actual helper outputs, including errors and missing
   inputs. Supply exact output hashes; do not author substitutes to obtain a pass.
2. Build a plan selecting typed claims and exact output pointers. Optional prose
   is registered as `unverified`; every such character span remains unaudited.
3. Render a draft, then audit that exact saved file. Review unsupported claims,
   counterexamples and every unaudited span before finalizing the draft. This
   happens before immutable first-response publication, not as post-hoc repair.
4. Publish those same finalized bytes as the first response and seal them under
   the existing capture controls. Any edit requires a fresh prepublication audit;
   the report tool does not seal, publish, rewrite an earlier response or confer
   comparison acceptance.

```text
python -B scripts/report_claims.py render report-plan.json artifact-root rendered.json --report draft.md
python -B scripts/report_claims.py audit report-plan.json artifact-root audit.json --report draft.md
```

Outputs use exclusive creation. Dependencies are the packaged `news_evidence`
reader and `source_claims` accounting contract (with its own packaged dependencies).
No network, installation or external service is used. The input output-artifact
limit is 16 MiB each; rendered/saved report limit is 128 KiB.

## Plan

```json
{
  "artifacts": {
    "scenario": {"path": "terminal-output.json", "sha256": "EXACT_OUTPUT_SHA256"}
  },
  "segments": [
    {"claim": {
      "id": "joint-condition",
      "kind": "scenario_condition",
      "evidence": {"artifact": "scenario", "pointer": "/objective_evidence"},
      "objective_id": "explicit-return-objective",
      "connective": "all",
      "conditions": [
        {"parameter": "terminal_ebit_margin", "operator": ">", "value": 0.1},
        {"parameter": "exit_ev_to_ebit", "operator": ">", "value": 4}
      ]
    }},
    {"unverified": "Qualitative discussion belongs here and requires separate review."}
  ]
}
```

Each claim has a unique ASCII identifier and an exact JSON pointer into a pinned
artifact. No caller-written claim conclusion, objective alias, accounting label
synonym or custom renderer is accepted. Optional assertion fields can demand a
supported relationship; they cannot change computed evidence.

### Scenario conditions

`scenario_condition` consumes the `objective_evidence` object from the terminal
helper. Name its exact `objective_id`, specify supported numeric parameter
conditions and `connective: "all"` (AND) or `"any"` (OR). Optional `assertion` is
`necessary`, `sufficient` or `necessary_and_sufficient`; unsupported assertions
are rejected before rendering.

The adapter rechecks row objective values against their numeric target/operator,
target definition and dimensions, then recomputes condition truth and witness
sets. It does not trust the old claim-status label. Rendered text includes the
actual measure/definition, connective, finite-domain size, counterexample IDs,
successes and unavailable rows. Empty success/condition sets are not proofs.
Unavailable DCF closure cannot inherit return evidence. The underlying terminal
model, original data and economic feasibility are not independently replayed.

### Accounting labels

`accounting_label` consumes a complete `source_claims` accounting result. Supply
`label: "diagnostic_ratio"`, `"basic_eps"` or `"diluted_eps"`. The adapter replays
the existing accounting contract against the retained bound fields and rejects
inconsistent classification, permissions, reasons, ratio or EPS. This is a
retained-field replay, not original-source authentication or source re-extraction.
The producer serializes Decimal operands as strings. Only retained numeric
`value` and `unit_scale` roles decode strict finite decimal strings for replay;
accounting metadata text is never coerced. Malformed/nonfinite strings fail.

A dated share count does not become weighted-average shares. A diagnostic remains
explicitly unscaled and is not EPS or P/E. EPS requires the existing contract's
source-bound accounting classifications. `pe` is deliberately unsupported because
this output has no independently bound comparable-price contract. Do not relabel
market-cap/income or dated-share arithmetic to bypass this gap.

### Latest selected cohort

`analyst_cohort` requires a complete `source_claims` `analyst_corpus` result,
including reconciled configured coverage and the actual analyst result. Plain
hand-selected rows or a standalone analyst result are insufficient. Optional
`assert_record_ids` must exactly equal the full selected record set.

The renderer includes every selected row, firm, target and issue time, plus all
exclusions. IDs/firms must be unique; selected and excluded IDs must partition
the coverage record set, and the retained firm count must agree. Unresolved,
unsupported or unlinked coverage blocks this route. No user-selected row subset
or numeric replacement is accepted. The adapter does not independently replay
original chronology or prove semantic completeness of the configured scan.
If required source metadata is absent, preserve that limitation; do not invent
URLs/timestamps to make this route run. Any separately discussed custom cohort
remains unaudited prose, not a certified latest cohort.

### Source presence versus adapter binding

`source_presence` consumes an actual `source_claims` `presence` output. It retains
the configured search terms, any/all match mode, scanned source IDs, unsupported
sources, lexical candidates, exact source references/hashes, and adapter binding
state/reason. The renderer checks that the retained predicate, candidate list,
permissions and facts agree. It does not rerun the original source search or
interpret accounting/property labels.

Optional `assertion` may be `source_candidate_present` when candidates exist, or
`adapter_value_bound` when the independent binding state is `EXACT_SOURCE_VALUE`.
Neither implies the other. Missing adapter binding cannot erase lexical source
evidence; exact adapter value identity cannot certify meaning. Null or invalid
bindings also establish no absence.

There is no allowed source-absence assertion. Even a complete configured search
with zero matches renders only `NO_CONFIGURED_LEXICAL_MATCH`; unsupported sources
retain `INCOMPLETE_SCAN`. Both states explicitly leave source absence and semantic
completeness unestablished. Arbitrary prose claiming absence remains unaudited,
or produces a saved-byte mismatch if inserted after rendering. Keep original
candidate references available for separate semantic review.

## Saved-response audit and interpretation

The audit re-renders from the pinned output bytes, then compares the entire saved
UTF-8 file, including whitespace. It records exact hashes and changed spans for
edited, appended, duplicated or missing content. A correct rendered block cannot
hide an altered surrounding conclusion.

- `SAVED_REPORT_MISMATCH`: the saved file differs from the planned rendering.
- `PARTIAL_UNAUDITED_PROSE`: byte consistency holds, but registered free-text
  spans remain unaudited. Even innocuous prose prevents an exact-bound-report
  status; contradictory prose can never become globally approved through this
  route.
- `EXACT_BOUND_REPORT`: every byte matches the fixed typed rendering; this is
  supplied-output consistency only, never whole-report semantic correctness,
  source authenticity, original calculation verification or a case pass.

Character spans are zero-based half-open Unicode offsets in the saved decoded
text when bytes match. On mismatch, expected/saved difference spans are retained;
planned unverified offsets then refer to the expected rendering. The report
still needs independent review of user-request coverage and all free prose.
Do not convert this bounded result into a general claim that the response is
verified or correct.
