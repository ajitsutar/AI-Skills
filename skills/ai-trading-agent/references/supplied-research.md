# One-run supplied-source research

Use this path for supplied-corpus analyst, REIT, issuer or source-claim research when its
producer contract fits the request. It joins the original corpus, actual producer
output, readable fixed report and saved-byte audit. It does not acquire sources,
submit orders, infer missing metadata or grade arbitrary prose.

Fractional JSON amounts remain exact decimal values during source parsing.
Calculation-input hashes encode finite decimals as their exact decimal strings;
they are normalized calculation hashes, not hashes of original file bytes.
The separately retained original request and source hashes bind those raw bytes.
Nonfinite decimals are rejected; no binary-float conversion is needed.

```console
python -B scripts/supplied_research.py run request.json --manifest SOURCE-INGRESS.json --manifest-sha256 EXTERNAL_PIN --source-root ORIGINAL_ROOT --output NEW_DIRECTORY
python -B scripts/supplied_research.py verify NEW_DIRECTORY
```

`NEW_DIRECTORY` must not exist and must be outside the skill. The manifest and its
SHA256 come from the supplied original inventory, independently of selected
analysis rows. Every manifest member is retained unchanged. Do not replace it
with a smaller corpus. Local files, not network URLs, are accepted.

The request has exactly `producer`, `producer_request`, and optionally
`unverified_prose`. No producer result, status, cached success, report text or
artifact hash can substitute for execution.

```json
{
  "producer": "source_claims",
  "producer_request": {
    "operation": "presence",
    "terms": ["cash"],
    "match": "any"
  }
}
```

The example configures a lexical search, not a semantic finding or source-absence
claim. Choose terms and bindings from the actual request and originals. Supported
producers are `analyst_sources`, `reit_sources`, `issuer_evidence` and `source_claims`; their nested
request retains the respective documented contract unchanged. There is no
automatic target-horizon, accounting-basis, firm-identity or role inference.

The [issuer evidence](issuer-evidence.md) producer binds a supported original
disclosure record and derives financial diagnostics and attributed business
context. For a generated-only final answer and matching structured response,
compose an `issuer_facts` section using the [final report](final-report.md) path;
the bridge's optional unaudited prose does not satisfy that strict contract.

The bridge performs these stages in one invocation:

1. Retain exact request, externally pinned manifest and every original source.
2. Call the selected producer against that retained corpus; save every result
   field in `result.json`, including rejected, unknown and partial outcomes.
3. Generate `report.md` from the producer's fixed report, or a small fixed source
   claim projection. The complete structured evidence remains linked separately.
4. Call the producer again against retained originals, compare its full result,
   regenerate the report, and compare the saved report bytes.
5. Save `audit.json` and `receipt.json` binding all retained artifacts and the
   installed Python implementation. `verify` independently repeats the replay
   and report comparison without editing the run.

These producers are pure offline analysis, not stateful broker/host operations.
No original workflow actions are repeated by this bridge. Failures preserve
`failure.json` and all earlier stage files; no completed receipt is produced.
Use a new output directory for a justified changed request. Never erase or
overwrite the failed attempt.

`COMPLETED_SOURCE_REPLAY_AND_REPORT_MATCH` describes execution and consistency,
not a successful investment thesis or complete answer. The audit always retains
`whole_report_semantic_pass=false`, `source_authenticity_verified=false`, and
`execution_authorized=false`. Producer rejections and incomplete coverage are
not promoted by a matching replay. All optional prose is visibly marked
unaudited, even when its bytes match exactly.

Review those limitations and all remaining interpretation before finalizing an
answer. If this report is used as a first response, publish its unchanged bytes
after the substantive commands finish and preserve the audit/receipt alongside
the existing capture seal. Editing the saved report makes verification fail.
The bridge does not force a host to follow this path or certify unrelated prose.

Input/request/result files are bounded to16MiB each, retained source corpus to
128MiB, source count to10,000, report to1MiB and optional prose to128KiB. Linked
or reparse paths are rejected. Receipts are local consistency records, not
tamper-proof attestations against someone rewriting every file and its hashes.

Python API: `run(request_path, output_dir, manifest_path,
expected_manifest_sha256, source_root=None)` and read-only `verify(directory)`.
