# Complete source context before allocation exposure

`source_exposure.source_allocation_context(document)` is the implementation for
`planning.source_allocation_context`. It composes the existing
`portfolio_decision.allocation_context`; the caller must supply scenario gross
notionals and an explicit denominator. It never selects a fund, creates weights,
changes preferences, ranks alternatives, or creates an execution gate.

The input has `schema_version: 1`, `currency`, `role`, `denominator`, `rows`, and
`sources`. Rows use the existing allocation schema (`id`, exact `symbol`,
`notional`, `notional_basis: gross_notional`, optional currency/period/provenance).
Denominator uses `amount`, `basis`, currency/period/provenance. Neither notionals
nor denominator are reconstructed from budgets or assumed account balances.
Rows cannot override source classifications, volume, or holdings.
Native adapters accept only the root binding; use explicit collections for another
layout. Conflicting recognized instrument classifications are exposed without
selecting a preferred declaration. Known issuer labels remain usable as type
`other` when an instrument type is unavailable; this is not an equity assertion.

Each source has a unique `id`, **whole original UTF-8** `text`, exact bytes
`sha256`, explicit `role` and `provenance`, `adapter`, and `bindings.root` (an
RFC6901 pointer; empty string explicitly selects the complete root). Keep source
role separate from the scenario role. Text is hashed before JSON parsing; duplicate
JSON keys and nonfinite numbers are rejected. This binds bytes, not authenticity.

Supported adapters:

- `portfolio_context_v1`: root-object `identities` and `other_identity` maps
  keyed by exact symbol, plus **all** root `funds` rows. Fund schema uses `symbol`,
  `holdings` array (`symbol`, `weight`), `holdings_coverage`, `holdings_as_of`, and
  optional `average_daily_dollar_volume`. Every fund's entire original record and
  list survive, including alternatives absent from the selected allocation.
  Recognized kind mappings are `common_stock` to equity, `ETF` to fund, and
  `cash` to cash. Fund collection membership establishes fund type.
- `business_statements_v1`: **all** root `issuers` rows, exact symbol,
  supplied classification fields and qualitative `business_description`, plus
  each `raw_snapshot_facts.adv20` observation and its literal unit, source ID,
  period and observation timestamp. A business description does not become an
  industry or issuer-ID label. Monetary `USD` alone does not establish a
  per-day/session/period-volume unit; its amount remains known while its ratio
  stays unresolved.
- `explicit_collections_v1`: explicit arrays of RFC6901 pointers under
  `bindings.identity_maps`, `bindings.funds`, `bindings.classification_rows`,
  `bindings.market_rows`. Identity maps use the same symbol-keyed identity
  objects; fund rows use the holdings schema above; classification and market
  rows have `symbol` plus supplied normalized fields. This is an explicit schema
  adapter, not a heuristic scanner. Unsupported schemas return `MAPPING_REQUIRED`
  and retain their complete source.
  Explicit collection lists cannot prove that the caller declared every available
  collection. They always retain `COLLECTION_INVENTORY_NOT_ESTABLISHED`, a partial
  context, and an unknown `all_declared_collections_consumed` completeness claim.
  Successfully consuming a caller subset does not certify whole-source coverage.

Normalized fields are `issuer_id`, `sector`, `industry`, `kind`, `share_class`,
`instrument_type`, `business_description`, and `dollar_volume`. A supplied
`dollar_volume` observation uses `amount`, `currency`, `unit`
(`currency_per_day`, `currency_per_session`, `currency_over_period`), period and
provenance. Use explicit source-bound supplemental rows when classifications or
market observations live in another packet; keep every such packet intact. An
amount in another currency does not create an FX model. Original observations
and declared supplemental observations that differ are conflicts, not overrides.

Exact symbols identify records; only an explicit shared `issuer_id` joins
classification across different symbols/share classes. No symbol spelling or
share-class suffix guessing is allowed. A literal `unknown` issuer ID is
unestablished and never joins symbols. Literal `unknown` sector/industry labels
are likewise unestablished: they cannot conflict with or override a known label.
Their original bindings remain retained. Known sector/industry supplied for an
established issuer can propagate with their bindings. Kind, share class and volume
do not propagate. Conflicting known labels remain null and are exposed with all
observations. Empty or whitespace-padded classification identifiers are rejected.
Known issuer/sector labels without an established instrument type are retained as
type `other`, with an explicit gap; this does not fabricate equity classification.
Conflicting instrument types remain `unknown` for exposure arithmetic. Neither a
separate kind label nor fund membership resolves a conflicting type declaration;
source records and all competing bindings remain available beside that unknown.

Return paths:

- `sources[]`: original text, byte SHA, canonical SHA, role, provenance,
  bindings, adapter and complete parsed document.
- `identity_context[]`: all symbols, merged `values` and per-field source
  `bindings`; `fund_context[]`: complete source record/binding and mapped context
  for every supplied fund, including unselected alternatives.
- `normalized_allocation_input`: exact input passed to the existing helper;
  `allocation_result`: its unchanged exposure, coverage, conservation, denominator
  and monetary-volume calculations/statuses.
- `mapping_status`, `mapping_gaps[]`, `mapping_conflicts[]`,
  `missing_classification_fields[]`: distinguish absent metadata, unknown type,
  unresolved mappings, issuer label conflicts, coverage mismatches and fund cycles.
  Cash classification is explicitly non-applicable.
- `complete_context_receipt`: consumed collection RFC6901 pointers and source
  evidence, counts, selected row IDs, and declared-adapter completeness scope.

Mapping statuses are `SOURCE_BYTES_BOUND`, `INPUTS_UNRESOLVED`, or
`MAPPING_REQUIRED`. Overall status is `COMPUTED_CONTEXT` or `PARTIAL_CONTEXT`.
Source binding completeness does not mean classification completeness, fresh data,
or proof of diversification. Missing industry/issuer, uncovered weights and
missing volume units remain visible. A coverage sum mismatch is reported without
renormalizing weights or inventing a residual asset label. Existing allocation
arithmetic alone computes exposure and notional-to-volume ratios.

Dependencies: Python standard library, `quant_common`, `report_facts`, and
`portfolio_decision` (its existing allocation dependencies are unchanged).
