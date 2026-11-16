# Native bound fund comparison

For a requested fund comparison, call `planning.fund_comparison_report` through
`scripts/quant_workbench.py`. This operation reuses `source_allocation_context`
and `friction_context`, then generates substantive Markdown, structured JSON and
a native summary from one source-bound record. Use `artifacts.markdown` as the substantive main report and
`artifacts.summary` as the substantive final-message content. Retain the exact
native JSON and all generated artifacts with their verification receipt. If the
host or task requires a response envelope, preserve that higher-priority output
contract and carry the native report or its substantive rows intact inside it.
An augmented envelope is not the exact native verified projection: retain and
verify the original generated JSON separately, and do not claim verification of
added envelope fields or free-form prose. A source-coverage map can be an annex;
it is not the comparison. Do not independently rebuild spread-dollar rows or
replace the generated role/horizon and current-holding sections with a coverage map.

## Input contract

The operation takes `schema_version: 1`, explicit `currency`, the complete original
`request`, optional `context_sources`, required `exposure_sources`, and optional
`friction_models`. Every source retains its complete UTF-8 `text`, `sha256`, and
unique `id`. Exposure sources use the existing [source-exposure](source-exposure.md)
contracts unchanged, including observation role, provenance, adapter and root.
They are consumed in full before fund comparisons are rendered. Each declared fund
is reported separately; declaring it as an alternative does not add an account position.

Request and context records require an explicit `scope` (for example one named
account). Same-field facts in the same scope must agree; identical duplicates keep
all provenance. Distinct scopes stay separate. Available context cannot be replaced
by caller flags such as unknown or complete. There are three bounded adapters:

- `fund_report_context_v1`, with `bindings: {"root": ""}`: the original structured
  object has `schema_version: 1`, `role`, `horizon`, `current_holdings`, and optionally
  `capital_use`, `liquidity`, `loss_tolerance`, `account_type`,
  `tax_jurisdiction`, `tax_residency`, `proposed_positions`, `future_positions`.
  The entire object is retained and all these field slots are inventoried automatically.
  Holdings are arrays of complete objects or complete symbol-to-position-value
  mappings; every member and its exact source value is retained.
  Missing, null and an actual empty collection have distinct states. This adapter is
  only for an original source in that schema, never a rewritten request masquerading
  as original evidence. Position amounts are retained but are not silently valued.
- `text_spans_v1`: bind original prose using field entries in `bindings`, each with
  UTF-8 byte `start`, exclusive `end`, and exact span `sha256`. Bound role/horizon
  text is retained and used in conditional assessment. This proves the selected text
  exists, not the semantic interpretation or completeness of original intent. It
  always produces a partial report. A holdings prose span is not parsed into an array.
- `json_pointers_v1`: explicit field entries in `bindings` are JSON pointers into
  the complete original object. Useful for other source schemas, but always partial:
  caller-selected pointers cannot establish whole-source inventory. Invalid/missing
  pointers remain `MAPPING_REQUIRED`; do not present them as absent source facts.

For prose requests, use the real source bytes and bound spans, not a fabricated
structured replacement. Bind available role and horizon and the actual portfolio
holdings source even though semantic coverage remains partial. A partial status
limits completeness claims; it does not excuse dropping available facts or assessment.
No natural-language parser or keyword completeness oracle is used.

## Quote, model and portfolio semantics

For the recognized portfolio fund records, `bid_ask_spread_bps` is a full bid-ask
quote observation. Exact Decimal lexical values and source pointer/hash are retained.
`quote_as_of` and `quote_reference_price_basis` are retained only when supplied;
`holdings_as_of` is never a quote timestamp. Missing, invalid and conflicting
observations remain unresolved. Numeric resource bounds are 128 characters and
absolute adjusted exponent at most 100, not a 0..1 weight test or economic ceiling.
An observed zero quote does not prove zero execution cost. Quotes are never charged,
halved, converted to currency or added to modeled costs automatically.

`friction_models` is keyed by declared fund symbol. Each entry has an explicit
`scenario_name` and an `input` using the existing friction contract, same currency,
and role `hypothetical_scenario` or `user_assumption`. These are visibly named
assumptions, never silently promoted to source facts. The source quote is supplied
by the report; callers cannot override `quoted_spread` in a model input. Retain
original cost assumptions in the supplied source corpus and explain any model
mapping/limitations. Unknown reference, phase or overlap remains native unresolved.
The native `applied_costs` array is the only applied-cost field rendered. This route
does not calculate a currency cost from notional; use a separately named native
sizing scenario when that calculation is required, preserving the native model.

Context numbers preserve exact original decimal tokens before conflict checks and
rendering; no binary-float comparison can merge distinct source quantities.

Composition uses the existing exact total-fund weight evidence, including unknown
remainder and denominator labels. Known issuer and sector weights aggregate on the total-fund denominator while
unknown composition remains visible. Supplied issuer identity joins direct current
holdings across share classes. All recognized current holding records are retained,
including unknown identities and current funds. Current fund positions are explicitly
outside this direct-issuer overlap calculation; no false zero exposure is asserted.
No account allocation, full-account completeness, purchase of an unheld alternative,
future grant or proposed trade is inferred. Use existing allocation operations for
separately bound gross-notional scenarios when requested.

The generated assessment uses the actual bound role/horizon, known equity exposure,
concentration and current issuer overlap. Conditional branches explain use-date loss
risk, capital preservation, liquidity and missing personal constraints. It does not
infer equity from the word fund, promise recovery, set a universal holding period,
or invent an overall ranking. Retained fees, tracking/benchmark and distributions
remain separate observations, not total returns or a same-benchmark skill ranking.

## Delivery verification and limits

`render_report(report)` reconstructs the report from the retained exact input and
rejects a changed canonical field. `verify_delivery(input, delivery)` regenerates
and compares all three projections and hashes. Removing a bound holding/horizon,
editing only a cost in the summary, or substituting a coverage map fails verification.
The CLI operation returns the report, artifact strings and their hashes; write those
strings exactly. Preserve the captured execution and original source corpus.

`COMPLETE_FOR_BOUND_SCOPE` concerns the finite supported inventory, not source
knowledge or authenticity. Legitimate null/absent facts remain visible. Unsupported
or subset mappings are `PARTIAL_BOUND_REPORT`. External accounts, arbitrary extra
host prose and semantic completeness of unstructured intent are never certified.
This is a portable invoked helper with no server, account action or execution gate.

## Separate observed metrics and criterion comparisons

The native portfolio schema recognizes `annual_expense_ratio` as an annual fraction,
`average_daily_dollar_volume` as currency per day with currency from the bound root,
`tracking_difference_last_year` as a signed fund-minus-benchmark return fraction,
and `distribution_yield` as a distribution fraction with period unspecified unless
`distribution_yield_period` is supplied. Exact source decimal values, percent/bps
conversions, periods, benchmark identities, currency, source pointer/hash and source
observation date are retained. Source fields with other names/units are retained raw
and remain unmapped; no semantics are guessed. Root source date is never a quote time.

The report compares annual expense observations and their bps difference without a
return forecast; separately compares dated same-currency volume observations with
unknown-lookback and execution limits; and explains quoted width without converting
it to one-way cost. Tracking comparisons preserve benchmark and period boundaries,
never relabel tracking difference as tracking error or subtract expenses again.
Distribution observations preserve missing periods and unknown tax character and
never become total returns. Tax discussion is conditional on bound account type,
jurisdiction/residency and distribution character; no local tax rule/rate is guessed.
These are criterion-specific observations and conditional interpretations, not an
overall fund ranking or invented user preference.
