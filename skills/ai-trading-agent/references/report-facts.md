# Deterministic report facts

The installed `profiles/report-facts-v2.json` also maps supported cash, financial,
strategy, forward-evidence and comparison result fields. Its identity is included
in the current workbench hash. Unmapped fields retain explicit unknown metadata;
an input's currency or holding horizon does not establish its amount scale or
observation frequency. Supported historical workbench schema fingerprints retain
their known original labels, with `known_historical_schema` reported separately
from `code_mapping_matches`. Historical interpretation is not current-code replay.

Use `scripts/report_facts.py` when a report needs a traceable table of values from
a retained quant-workbench bundle or public VQM ranking bundle. This optional
adapter copies values and names supported metrics; it does not calculate returns,
replay a job, authenticate observations, validate arbitrary prose or impose any
condition on host execution. Existing helper `verify` commands remain separate.

When reporting numeric conclusions supported by those outputs, use the retained
named facts with their units, denominator and horizon, whether read directly or
exported through this adapter. Identify additional calculations and inference
separately; retain the existing helper result or calculation code for new
numbers. Unknown metadata remains unknown in the report. This is reporting
guidance for supported conclusions, not a requirement to render every response.

```text
python scripts/report_facts.py quant /private/run/quant.bundle.json --private-output /private/run/facts.json
python scripts/report_facts.py public-vqm /private/run/ranking.bundle.json --format markdown --private-output /private/run/facts.md --include-source-text
```

The output must be outside the skill and must not already exist. The CLI reads
local files only, writes one explicitly requested file, and prints no source
values. It never follows paths or URLs embedded in JSON. Review the local output
before sharing it. There is no credential-redaction or public-release guarantee:
amounts, pointers, declared horizons and custom labels can themselves be private.
By default nonnumeric source strings in fact values are withheld, except known
helper status codes. `--include-source-text` explicitly includes selected labels,
warnings, limitations and rejection reasons. It does not copy the whole input or
contract prompt. Markdown treats imported text as literal content, not embeds.

Every fact carries the source artifact's exact byte SHA-256 and an RFC6901 JSON
pointer, value, unit, denominator, basis, declared research horizon, assumptions
and missingness. `null`, absent and withheld source text are different states.
Measurement period and observation frequency remain explicitly unknown; the
declared contract horizon does not supply them. Embedded input metadata is joined
to quant results only when its content hash and unique job ID/operation match.
Hashes establish content consistency, not execution or source authenticity.

Built-in metric labels are conditional on matching local implementation/profile
fingerprints. They cover quant tail/portfolio returns, HAC means, XIRR,
attribution and shortfall, plus public VQM corporate and financial factor
definitions. Other fields remain unmapped, with unknown units and basis. In
particular, a return-series drawdown is not labeled account drawdown; portfolio
simulator drawdown refers to modeled portfolio equity. Corporate VQM income over
average assets is ROA; financial common income over average common equity is ROE.
Scores retain ties and their exact decimal strings. Sequential queue positions
do not imply strict factor superiority or investment eligibility.

Both wrapper computation status and nested result status are retained. A
`COMPUTED` wrapper can contain a nonconventional-XIRR or infeasible-allocation
result; a rejected job never contributes stale numeric result fields.
Public VQM scores are projected only for the helper's `RESEARCH_QUEUE_ONLY`
status; missing or unsupported status retains the status/reason without scores.
Legacy execution/permission flags are omitted rather than interpreted as trading
decisions. Known status codes describe research computations only.

For a field without a built-in label, optional `--custom-bindings bindings.json`
selects exact pointers. It accepts no expressions, imports or formulas:

```json
{"facts":[{"pointer":"/result/results/0/result/mean","metric":"Declared sample mean","unit":"input return fraction","basis":"Analyst-declared sample definition","horizon":"Declared study horizon","assumptions":["Frequency requires separate evidence"]}]}
```

All such labels and metadata carry `CUSTOM_DECLARED_UNVERIFIED`, even when their
source pointer resolves. They add facts; they do not overwrite built-in facts or
certify a user's semantic claim. New numerical claims still need an existing
helper or separately retained calculation code. This adapter does not assess
whether the selected inputs, denominator or source joins were appropriate.

## Verify a retained projection

Verification recomputes the canonical projection from the original artifact and
compares the entire JSON structure, including fact order, types, metadata and
checks. JSON whitespace and object-key order may differ. Original source bytes,
custom-binding bytes, adapter/semantics fingerprints and source-text options are
bound exactly. Retain those source files alongside the report; a facts-only file
cannot establish what its original omitted. Custom bindings now have a top-level
`custom_bindings_sha256`, including an empty custom declaration, so omitted and
explicitly supplied bindings remain distinguishable.

```text
python scripts/report_facts.py quant /private/run/quant.bundle.json --verify-projection /private/run/facts.json --private-output /private/run/facts-check.json
python scripts/report_facts.py quant /private/run/quant.bundle.json --custom-bindings /private/run/bindings.json --include-source-text --verify-projection /private/run/extended-facts.json --private-output /private/run/extended-facts-check.json
```

Use the same custom bindings and source-text setting used for projection. The
candidate is always JSON; `--format markdown` changes only the diagnostic output.
Existing projection commands are unchanged. Verification writes its diagnostic
file privately and exits `0` for `VERIFIED_PROJECTION`, `1` for
`PROJECTION_MISMATCH` or `INVALID_PROJECTION`, and `2` for an invalid original,
invalid custom declarations, unavailable file/path or an existing output file.

Python callers can use
`verify_projection(raw, kind, projection_raw, custom_raw=None, include_source_text=False)`.
All raw arguments are UTF-8 JSON bytes. The returned dictionary includes `status`,
`matches`, `expected_bindings`, per-field `binding_matches`,
`metadata_mismatch_paths`, `facts_sequence_matches`, `builtin_facts`,
`custom_facts`, and `source_mapping_checks`. Fact diagnostics list missing, added
and altered records by fact index, source pointer and hash; altered records include
changed field paths without copying the selected values. Changed identities can
appear as missing plus added. Malformed candidate JSON/schema returns
`INVALID_PROJECTION`; invalid original/custom inputs raise the same exceptions as
`project()`.

Here **built-in facts** means every fact emitted before custom declarations,
including unmapped values, missingness, outer and nested statuses, warnings and
rejection reasons. It does not mean only facts with known built-in units. Keep
this complete canonical sequence when appending custom facts. A custom-only
projection, duplicated fact, silently dropped rejection, changed pointer, or
changed unit/value fails the comparison. A shorter reader-facing report may cite
selected canonical facts, but it is not the complete projection being verified.

`VERIFIED_PROJECTION` establishes consistency with the supplied source and local
adapter only. Inspect `source_mapping_checks` separately: an exact projection can
faithfully retain an unknown implementation or an inconsistent embedded hash.
Known historical source schemas remain marked `known_historical_schema`, with
`code_mapping_matches` and `calculation_replayed` false. A historical adapter's
export is not accepted as a current-adapter projection; retain it and make a
separate projection from the original when a current comparison is useful.
Verification does not authenticate sources, replay calculations, validate custom
semantic declarations or establish that selected inputs answer the research
question. In reports, identify additional source joins, inferred dates and causal
interpretations separately from the retained facts that support them.
