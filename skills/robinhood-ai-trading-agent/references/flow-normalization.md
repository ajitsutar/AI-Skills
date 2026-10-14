# Explicit observation mapping and flow normalization

Use `data.normalize_flows` / `flow_normalization.normalize_flows(document)` when supplied financial observations are not already in the installed financial normalizer's input format. An absent prebuilt schema is mapping work, not evidence that the financial data are missing. Map the supplied evidence explicitly, inspect mapping issues and normalized gaps, and retain the returned artifact for replay. Do not substitute a requested cash-flow measure with another profitability measure because mapping is unfinished.

This helper composes `financial_normalize.normalize`; it contains no separate TTM formula. The existing engine resolves exact TTM observations, four contiguous quarters, and annual plus current YTD minus prior YTD. It also owns duplicate rounding reconciliation, cutoff exclusion, accounting-basis checks, source readiness and unresolved amendment conflicts. A later amendment does not automatically erase a contradictory earlier observation.

## Input contract

The outer input has `flow_mapping_schema_version: 1`, an explicit timezone-aware `information_cutoff`, `sources`, `issuers`, `metric_mappings`, and `observations`.

Each source needs a unique `source_id` and exactly one retained byte representation: `source_text` (the exact text encoded as UTF-8, without whitespace normalization) or `source_bytes_base64` (exact original bytes). The helper computes the ordinary SHA-256 of those bytes. If a caller supplies `content_sha256`, it must match; a mismatch is retained as a mapping issue and excludes that source's observations. Hashes establish a byte binding, not authenticity. Do not replace original downloaded bytes with reconstructed text and call the resulting hash the original source hash.

Supply `uri`, `distribution_host`, `document_origin`, `delivery`, `retrieved_at` and `publication` from actual evidence. Publication uses either `{ "precision": "timestamp", "at": "...timezone-aware timestamp..." }` or `{ "precision": "date", "date": "YYYY-MM-DD", "timezone": "IANA timezone" }`. Date-only publication stays an interval; do not invent midnight precision. The existing engine treats incomplete or unsupported source declarations as unverified. No origin, SEC accession, primary-content match, or verification method is manufactured by this route.

`verification` is copied exactly when supplied and otherwise defaults to `{ "status": "unverified" }`. Explicit claims of verification remain visible in both the mapping input and the normalizer input. This offline helper cannot authenticate those claims. The downstream engine's source readiness is conditional on the declarations and supporting evidence, not a new independent verification by this helper.

Each issuer supplies `issuer_id`, `entity_id`, `adapter`, `ttm_start`, and `financial_period_end`. Supported adapters are the installed normalizer's `corporate`, `equity_reit`, `bank`, `insurer`, and `other_financial`. Each observation explicitly identifies the same issuer and primary entity. This minimal mapping route does not infer entity aliases or automatically remap predecessor observations. More involved predecessor mappings can use the existing normalization schema directly.

`latest_public_period_review` is optional and is never generated. Without its explicit supported declaration, the engine emits `LATEST_PERIOD_UNREVIEWED` and `latest_public_period_checked: false`. Computing a trailing value does not establish that it is the latest public period.

`metric_mappings` maps caller metric labels to objects with:

- `concept`: an exact installed policy key from `profiles/financial-normalization-v1.json` under `tags` or `reviewed_concepts`; for example `cfo`, `ppe_capex`, `other_productive_capex`, or `parent_income`. These are explicit choices, not guessed aliases.
- `review`: `{ "status": "reviewed", "basis_evidence": "specific supporting evidence for the concept mapping" }`. Without the declaration, the observation remains unmapped. The helper associates an explicit review with the current policy hash; a supplied different policy hash is rejected.
- `basis`: the explicit accounting-basis code when the policy requires one. A supplied nonselected basis is preserved for the engine to reject. If an observation also declares a different basis, the mapping reports `OBSERVATION_MAPPING_BASIS_CONFLICT` rather than overwriting it. No code is guessed from a friendly metric label.

Each observation supplies `record_id`, `source_id`, `source_pointer` (a stable source locator), `quote`, `issuer_id`, `entity_id`, `metric`, `period_end`, `unit`, and `decimals`. Flows also need `period_start`; point-in-time facts omit it. Source pointers and quotations are retained caller assertions; they are not proof that the source is authentic. Provide `unit: "USD"` with an explicit value in dollars, or the display representation described next. Other currencies need a separately evidenced conversion process; the helper does not infer one.

Supply exactly one of `value` or `display_text`. For `display_text`, optional explicit `scale`, `sign`, and `format` go through the existing filing parser. A raw `value` cannot also carry display transforms. `decimals` describes reporting precision in the normalized unit, independently of scale; `-6` means reported to millions of dollars. The helper never supplies `INF`, zero precision, or extra decimal places. Use `INF` only when the evidence explicitly warrants exactness. Missing precision is a mapping issue.

## Small invented example

This single exact trailing observation illustrates the route; it does not demonstrate a complete issuer financial statement or authenticated source.

```json
{
  "flow_mapping_schema_version": 1,
  "information_cutoff": "2026-04-30T23:00:00Z",
  "sources": [{
    "source_id": "supplied",
    "source_text": "Invented cash-flow table: operating cash 740 USD for 2025",
    "uri": "urn:example:supplied-cash-flow",
    "distribution_host": "local",
    "document_origin": "supplied_observation",
    "delivery": "local",
    "publication": {"precision": "timestamp", "at": "2026-03-01T12:00:00Z"},
    "retrieved_at": "2026-04-20T12:00:00Z"
  }],
  "issuers": [{
    "issuer_id": "example-issuer",
    "entity_id": "example-entity",
    "adapter": "corporate",
    "ttm_start": "2025-01-01",
    "financial_period_end": "2025-12-31"
  }],
  "metric_mappings": {
    "reported operating cash": {
      "concept": "cfo",
      "review": {
        "status": "reviewed",
        "basis_evidence": "Invented table identifies consolidated reported operating cash, without adjustments"
      }
    }
  },
  "observations": [{
    "record_id": "operating-cash-2025",
    "source_id": "supplied",
    "source_pointer": "table:operating-cash",
    "quote": "operating cash 740 USD for 2025",
    "issuer_id": "example-issuer",
    "entity_id": "example-entity",
    "metric": "reported operating cash",
    "period_start": "2025-01-01",
    "period_end": "2025-12-31",
    "value": "740",
    "unit": "USD",
    "decimals": 0
  }]
}
```

The result includes the draft `cfo_ttm` and unresolved source/latest-period and other financial gaps. For a free-cash-flow request, map all required productive-capex components from supplied evidence as well; never invent a zero for an absent component. A draft calculation does not authorize eligibility, ranking or execution claims.

## Output and replay

The returned artifact contains unchanged `mapping_input` and its deterministic digest, `mapping_issues`, the generated `normalization_input`, and `normalization` from the existing engine. It always sets `execution_authorized: false`. Source bytes and declarations remain in the input artifacts; normalized records retain the source pointer and the applied review. If mapping issues exist, outer status is `MAPPING_REQUIRED`; otherwise it is the engine status. Structural errors in the normalizer contract, such as invalid windows or duplicate record identifiers, retain the existing engine's error behavior.

The three schema roles are distinct:

- `flow_mapping_schema_version: 1` describes this observation mapping envelope.
- `normalization_input.schema_version: 1` describes financial normalization evidence. Replay with `financial_normalize.normalize(result["normalization_input"])` and compare against `result["normalization"]`.
- Scoring snapshot `schema_version: 2` embeds the normalization input as `financial_normalization` alongside the independent market and universe evidence. The mapping artifact is not itself a scoring snapshot, and the helper does not invent market facts or upgrade draft evidence to readiness.

Unknown metric labels or concepts, absent mapping reviews, missing source bytes, missing precision, or unknown entity/unit mappings are reported as mapping issues. Obtain and document the missing mapping or supporting declaration before treating the observation as canonical. Continue independent work using the supplied evidence where possible; a mapping issue alone does not establish missing financial data.
