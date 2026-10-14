# Ranking route, replay and comparison

`scripts/ranking_alignment.py` binds a supplied profile to an installed scorer.
It calls the existing `public_research.calculate(snapshot, count)` or
`vqm_research.calculate(snapshot)` unchanged. It does not create weights, rank by
a convenient substitute metric, fetch inputs, estimate returns or impose an
execution prerequisite.

## Python interfaces

All three operation functions accept one JSON-compatible dictionary and return
one JSON-compatible dictionary. `installed_routes()` returns the installed
profile IDs, versions, canonical hashes, supported snapshot schemas and scorer
source hashes. Installed profile/source text hashes normalize platform line
endings, so the same installed logic can replay across operating systems. Supplied
source byte hashes remain exact; canonical JSON hashes separately identify profile
meaning. Input documents require `schema_version: 1`.

### `route_ranking(document)` and `replay_ranking(document)`

```python
document = {
    "schema_version": 1,
    "profile": {"text": retained_profile_json_text, "sha256": utf8_bytes_sha256},
    "snapshot": retained_snapshot_document,
    "requested": {
        "profile_id": requested_profile_id,
        "profile_sha256": requested_canonical_profile_sha256,
    },
    "selection_count": positive_integer,  # required for public, optional for strict
    "allow_diagnostic_replay": False,     # optional; false by default
}
```

`profile.text` is the exact retained UTF-8 JSON text, including whitespace. Its
`sha256` hashes `text.encode('utf-8')`. Duplicate JSON keys and nonfinite numbers
are rejected. The snapshot is supplied directly as JSON; its canonical hash is
retained in the receipt. A snapshot hash does not authenticate its economic facts.

The profile's **canonical JSON hash** must equal an installed profile and
`snapshot.profile_sha256`. Canonical JSON uses sorted keys, compact separators,
`ensure_ascii=False`, and `allow_nan=False`, matching the scorers. Whitespace can
change the supplied byte hash without changing profile identity. Public snapshots
support schema 1. Strict snapshots support schema 1 (declared-fact replay) and
schema 2 (shared normalization); original scorer assurance labels are preserved.
Neither schema is silently relabeled as another. A recognized profile with an
unsupported snapshot schema has no bound route.

`requested` accepts only the two fields above: a free-form method name cannot
override its declared profile identity. An absent/incomplete request is `UNKNOWN`.
An explicit other method is `DIFFERENT`. A complete matching request is `SAME`.
The receipt separately retains `requested`, `requested_route`, and
`available_diagnostic_route`; it never calls a profile stale solely because a
different installed scorer rejected it.

`route_ranking` does not run a scorer. `replay_ranking` runs a matching requested
route, or an available diagnostic route **only** when
`allow_diagnostic_replay=true`. A diagnostic result is returned solely under
`diagnostic_result`, with `requested_result=null`. Diagnostic availability cannot
satisfy the requested method. A mismatched/missing profile or unsupported schema
cannot be rescued by the diagnostic flag. Scorer input errors retain the error
and return `SCORER_INPUT_ERROR` without a fallback ranking.

A successful replay preserves the complete original scorer output. The separate
`selection` is an order-preserving projection, with its result scope explicitly
labeled. Optional strict selection count never changes the strict scorer or its
scores. `ranking_execution_verified=true` establishes this adapter invocation,
not any earlier model run. Implementation hashes cover the named installed scorer
file with CRLF normalized to LF; they are not a complete dependency/runtime lock.
Raw scorer fields remain raw evidence, including any legacy field names.

### `compare_rankings(document)`

```python
document = {
    "schema_version": 1,
    "identity_field": "symbol",  # or issuer_id; choose explicitly for both sides
    "left": {
        "sources": {"run": {"text": retained_json_text, "sha256": utf8_bytes_sha256}},
        "bindings": {
            "method_profile": {"source_id": "run", "pointer": "/profile"},
            "snapshot": {"source_id": "run", "pointer": "/input"},
            "candidates": {"source_id": "run", "pointer": "/result/research_candidates"},
            "scores": {"source_id": "run", "pointer": "/result/scores"},
            "classifier_available": {"source_id": "run", "pointer": "/result/strong_buy_available"},
        },
    },
    "right": other_side_sources_and_bindings,
    "max_snapshot_differences": 1000,  # optional positive output limit
}
```

Each side can retain multiple sources. Bindings are explicit RFC6901 JSON pointers,
never expressions or natural-language field guesses. Optional dimensions are
`horizon`, `preferences`, and `review_decisions`; bind them only to the relevant
retained records. A strict ranking can bind `candidates` to `/discovery_order`.
Candidate lists may contain identity strings or records containing the selected
identity field. Array order defines candidate positions. Scores are records with
that identity field and a numeric or null `score`. Duplicate identities are rejected.

Output keeps these questions separate:

- Candidate membership, positions, counts, fractions of each supplied list and
  Jaccard overlap. An empty denominator produces null, never 100% agreement.
- Numeric score differences, unobserved scores and retained profile comparability.
  Different/unknown methods remain labeled even when their score numbers match.
- Snapshot field differences with source pointers, explicit missing-field markers,
  total difference count and any output truncation. List position is preserved;
  this is structural comparison, not an inferred business-key join.
- Exact supplied profile identity, horizon, preferences and review-decision records.
  Both missing is `UNKNOWN`, as is an empty metadata object/list. Explicit absence
  of a preference can instead be represented by an affirmative record such as
  `{"mode":"none"}`. Null or absent bindings are not treated as equal decisions.
- Boolean classifier availability. Two false declarations can agree about
  classifier unavailability, but `per_name_buy_eligibility` remains `NOT_ASSESSED`.

Method profile comparison requires supplied profile objects with ID and version;
it compares their full canonical contents, including parameters. It can compare
uninstalled profiles structurally but does not claim their scorer ran. Comparison
does not replay or certify earlier ranking outputs; use `replay_ranking` separately.
There is no overall alignment percentage, pass threshold or investment verdict.
All output includes the input hash, source byte/canonical hashes, bindings and
limitations. Hash agreement cannot establish correct source selection, source
authenticity, calibrated forecasts or independent acquisition.

## Local command line

```text
python scripts/ranking_alignment.py route request.json
python scripts/ranking_alignment.py replay request.json
python scripts/ranking_alignment.py compare comparison.json
```

The CLI reads its explicit local input and prints JSON. Save private run inputs and
outputs outside the installed package. No URLs or code named inside inputs are
executed.
