# Original-source leaf lineage

Exact hashes of a model-created calculation request establish reproducibility of
that request. They do not establish that its accounting labels came from the
original evidence. Use `scripts/source_lineage.py` when the task supplies a
separately frozen original-source manifest and its expected SHA-256 hash.

The user or controlling workflow must anchor that expected hash before the
participant's analysis. Do not create a new manifest around your own derived
request and present it as the original-source root. If no external anchor exists,
disclose that limitation; a descriptive role such as “original request” cannot
replace it. This remains an optional research assurance capability, never a host
action requirement or an authentication service.

The manifest is JSON with `schema_version: 1` and `sources`, a list of objects
containing exactly `id`, `path`, `sha256`, and `format` (`json`, `text`, or `bytes`).
Paths are relative to the manifest directory unless `--source-root` is supplied;
all resolved paths must remain in that root. Every file is hash-verified before
any mapping is evaluated. No file content is fetched or inferred.

Each explicit mapping contains exactly `target_pointer`, `source_id`, and
`source_pointer`. Both pointers must select scalar JSON leaves. No parent-object
inheritance, inferred reporting periods, matching-value search, prose extraction,
authorship flag or arithmetic transform is supported. Original nulls remain
unknown. Type and value must match, so true does not equal 1. Text originals can
be retained in the manifest but cannot supply a JSON leaf mapping. Unsupported
extractions remain separately reviewed declarations, not automatically proven
facts.

```sh
python scripts/source_lineage.py --manifest original-manifest.json \
  --manifest-sha256 EXPECTED_SHA256_FROM_TASK \
  --target calculation-input.json --mappings original-leaf-mappings.json \
  --required-pointers required-fields.json --output lineage-report.json
```

`required-fields.json` is an explicit list of target pointers. The report covers
every required field, including unmapped ones. `MATCHED_ORIGINAL_VALUE` means only
that the selected leaf has exact original identity under the supplied pin.
`UNKNOWN` keeps missing mappings or original nulls unresolved. `INVALID` reports
a contradictory mapping, absent source/pointer, non-leaf value, or mismatched
value. Structural or hash errors fail before a result is written. An output path
must be new; no previous result is overwritten.

## REIT metadata view

For a REIT document, use the built-in enumeration instead of choosing only the
easy fields. It checks unit, period and holder basis for every supported group,
and denominator/time-anchor metadata for property fractions:

```sh
python scripts/source_lineage.py --manifest original-manifest.json \
  --manifest-sha256 EXPECTED_SHA256_FROM_TASK --target reit-document.json \
  --mappings reit-original-mappings.json --reit-metadata \
  --output reit-lineage-report.json --masked-document-output reit-original-view.json
```

Mapping targets begin with `/document/`, for example
`/document/cfo/basis/period_end`. The source pointer names the actual leaf in an
original source. A legitimately supplied full workbench request can itself be a
manifest original; its genuine inline leaf is supported. A later authored request
is not an original merely because its role says so.

The report retains `declared_document` and `original_lineage_document`. The
second keeps original amounts and masks metadata without original leaf lineage
to null. Run normal REIT reconciliation on the appropriate original-lineage view
and retain the declared reconciliation alongside it. Do not erase a declared
`INCOMPATIBLE` basis by replacing it with an unknown label. Unknown basis permits
only explicitly conditional arithmetic, not an actual payout shortfall or
unqualified cross-measure compatibility claim.

Identity is still distinct from scope. A period copied from the wrong issuer or
measurement group can match an original leaf while being inappropriate for the
target. Review source scope separately. The helper reports
`source_authenticity_verified: false`, `semantic_scope_verified: false`, and
`external_anchor_origin_verified: false`; it cannot prove who supplied the pin,
when it was created, that disclosures are true, or that the original set is
complete. It does not validate arbitrary final prose.
