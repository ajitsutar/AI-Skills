# Source-bound issuer research

Use `scripts/issuer_evidence.py` for business research from retained financial
disclosures. It produces financing, cash conversion, dilution, business context,
capital allocation and valuation-limit sections from original fields. Combine
these with separately evaluated terminal/objective sections when needed.

The adapter does not interpret arbitrary prose as financial facts, certify a
covenant, authenticate a publisher or decide that an investment is undervalued.
It supplies concrete arithmetic and attributed descriptions while retaining
unknown dates, dimensions and model requirements.

## API and final reports

```python
result = issuer_evidence.analyze(
    request, manifest_path, expected_manifest_sha256, source_root=None)
```

The manifest is the externally pinned complete original-source inventory used
by the supplied-source workflow. Every indexed file is hash-verified, including
unselected files. No acquisition or network operation occurs. Explicit record
selection does not establish semantic review of every original source.

The closed request schema is:

```json
{
  "issuer_record": {"source_id": "filing", "pointer": "/issuers/0"},
  "peers": [{"source_id": "filing", "pointer": "/issuers/1"}],
  "monitoring": ["funding", "cash_conversion", "dilution", "business_position", "capital_allocation", "valuation_objective"],
  "research_stance": "undetermined"
}
```

Only `issuer_record` is required. Peers default to none (maximum eight distinct
issuer identities). Monitoring defaults to all six topics; a supplied list may
select a nonduplicated subset. Stance is `watch`, `undetermined` or
`further_research`, always rendered as an uncomputed opinion. Unknown request
keys, caller numeric overrides, role mappings, report labels and prose are
rejected. Aliases of the same original record cannot create extra peers.
An optional typed `research_plan`, described below, adds conditional thesis
review, invalidation criteria, selected event context and a proposed cadence.

For a JSON object embedded in text, a record reference additionally supplies
`start`, `end` and `excerpt`; these are exact decoded-character offsets for the
whole JSON span. `pointer` is relative to that parsed span. Duplicate keys,
nonfinite JSON tokens, altered excerpts and references outside the original
manifest are rejected.

The result is deterministic JSON-compatible data. It contains `issuer`,
`original_facts`, `funding_comparisons`, `point_changes`, `covenant_diagnostic`,
`cash_operating`, `business_context`, `capital_allocation`, `valuation_objective`,
`monitoring_hypotheses`, `research_plan`, `topic_coverage`, `source_coverage`, `limitations` and
`report`. `report` contains exact `text`, its UTF-8 `sha256`, and
`whole_report_semantic_pass: false`. Numbers calculated from Decimal inputs are
decimal strings; original numeric tokens and source references remain retained.
No runtime directory, wall-clock timestamp or random identity enters the result.

The final compositor's `issuer_facts` section accepts `kind` and `request`.
Retain the entire result in canonical analysis, not a caller's flattened metric
dictionary. For the supported structured research contract, use generated
sections and the canonical response projection together; arbitrary commentary
does not acquire a verified status by being adjacent to them. See
[final report composition](final-report.md).

## Conditional thesis and rolling review plan

Generic monitoring questions alone do not supply requested invalidation rules
or an event review plan. When those are requested, include a `research_plan`:

```json
{
  "cadence": "QUARTERLY",
  "rules": [
    {"purpose":"REVIEW_THESIS", "metric":"ebit_margin_fraction", "operator":"lt",
     "threshold":{"kind":"ANALYST_ASSUMPTION", "value":0.18}},
    {"purpose":"INVALIDATE_HYPOTHESIS", "metric":"cfo_less_capex", "operator":"le",
     "threshold":{"kind":"ANALYST_ASSUMPTION", "value":0}}
  ],
  "as_of_ref":{"source_id":"filing", "pointer":"/as_of"},
  "event_window_days":90,
  "events":[{"source_ref":{"source_id":"filing", "pointer":"/events/0/description"},
             "date_ref":{"source_id":"filing", "pointer":"/events/0/event_date"}}]
}
```

This object is the value of the request's `research_plan` key. `cadence` and a
nonempty list of at most16 `rules` are required. Cadence is `ON_NEW_SOURCE`,
`MONTHLY` or `QUARTERLY`: a proposal only, never an installed schedule. A rule has
exactly `purpose`, `metric`, `operator` and `threshold`. Purpose is
`REVIEW_THESIS` or `INVALIDATE_HYPOTHESIS`; comparison is `lt`, `le`, `gt`, `ge`
or `eq`. Include both purposes when the request asks for both. `purpose_coverage`
reports what was supplied and does not silently fill a missing purpose.

Metrics are the named diagnostic metrics under `cash_operating` (such as
`cfo_less_capex`, `ebit_margin_fraction`, `net_debt` or
`cash_after_capex_acquisitions_distributions`), plus
`shares_point_change_percent` and `revenue_point_change_percent`. The latter use
**percent relative change**, not percentage points or an inferred annual rate.
Observed values are always derived from the retained disclosure. A caller cannot
supply a cached observation, change its label or append a narrative condition.
Money metrics use their disclosed nominal currency and scale; margins use
`fraction`, valuation/coverage ratios use `ratio`, point changes use `percent`.

`ANALYST_ASSUMPTION` requires only a finite numeric `value`, interpreted in that
metric's displayed unit/scale. It is prominently labelled a proposed research
policy choice, not an original observation or necessary condition for value.
Alternatively use `{"kind":"SOURCE_THRESHOLD","source_ref":OBJECT_REF}`.
The original threshold object must contain `metric`, `value`, `unit` and
`unit_scale` matching the selected metric. Optional original `issuer` must match
when present; absent issuer remains `UNSPECIFIED_RESEARCH_POLICY_SCOPE`, with the
chosen application issuer disclosed separately. No issuer attribution is filled
in. Threshold records are research-policy inputs, not proof of investment truth.

Cash/operating metrics with missing or incompatible dates/dimensions yield an
`UNKNOWN` rule evaluation. Point-change rules retain their explicit point-only
scope; reversed dates cannot establish a rule outcome. Unknown is neither a
satisfied nor a failed condition. A matched invalidation condition applies only
to the chosen metric-bound research hypothesis, not to every investment thesis,
DCF closure, general business necessity or a trading authorization.

At most16 event entries preserve exact original text leaves/spans. An optional
`date_ref` must select the same structured object's `event_date`, or an original
date span contained inside the quoted text event. Dates cannot be borrowed from
another record or typed into the request. `as_of_ref` selects an original ISO
date or offset-bearing timestamp; `event_window_days` is30,90(default) or365.
Known dates yield a calendar-day past/within-window/outside-window diagnostic.
Offset-bearing timestamps are normalized to UTC; date-only fields retain their
calendar date. Missing/unsupported date text remains visible with timing
`UNKNOWN`. A selected excerpt is not a verified occurrence or an exhaustive
near-term event inventory. Review additional sources where the user's scope
requires them; do not relabel a distant event as near-term.

The rendered plan calls for reassessment at the proposed cadence and upon new
original-source evidence, preserving prior observations and changes. This adds
concrete review and invalidation conditions without pretending to prove the
underlying valuation thesis. When `research_plan` is omitted its status is
`NOT_REQUESTED`; the six topic headings alone must not be cited as completion of
a requested conditional/rolling plan.

## Supported original schema

The selected object must have a source `symbol` and a `raw_snapshot_facts`
object. This is a bounded financial-disclosure adapter, not a field-name guessing
system. It reads these roles directly from that same object:

| Original structure | Roles |
| --- | --- |
| `raw_snapshot_facts/<role>/{value,unit,period_start,period_end}` | `cash`, `debt`, `ebit_ttm`, `net_income_ttm`, `cfo_ttm`, `capex_ttm`, `market_cap`, `preferred_equity`, `noncontrolling_interest` |
| Issuer scalar fields | `currency`, `unit`, optional `unit_scale`, `period_start`, `period_end`, `revenue`, `revenue_prior`, `gross_profit`, `interest_expense`, `income_tax_expense` |
| Share fields | `shares_diluted`, `shares_diluted_prior`, `share_count_as_of`, optional `share_count_prior_as_of` |
| Prior revenue timing | Optional `revenue_prior_period_start`, `revenue_prior_period_end` |
| `cfo_reconciliation_items` | `depreciation_amortization`, `stock_compensation`, signed `working_capital_change` |
| `capex_detail` | `maintenance`, `growth` |
| `capital_allocation` | `acquisitions_cash_paid`, `dividends_paid`, `buybacks` |
| `expense_disclosures` | `restructuring`, `acquisition_integration`, `annual_repeated_restructuring_occurrences` |
| `debt_maturities[]` | `principal`, `date`, optional explicit `currency`, `unit`, `unit_scale`, entity metadata |
| `revolver` | `commitment`, `undrawn`, original `covenant` quotation |
| Business context | Original `business_description`; `customer_concentration/largest_customer_revenue_fraction` |

Numeric roles require finite original JSON number tokens, not Boolean or quoted
number replacements. Missing or malformed fields remain visible; they do not
become zero. Supported numbers have at most 50 significant digits and adjusted
decimal exponent magnitude at most 100. Arithmetic uses a local 260-digit Decimal
context, so repeating ratios are rounded; no binary float conversion is required.

The disclosure currency applies to its nominal monetary fields. A raw fact with
its own unit retains that scope. Supported unit labels are the exact currency
code or a declared literal-unit parenthetical annotation; positive magnitude
prose such as `USD millions` is not normalized or guessed. Explicit numeric
scales must be positive and compatible; unknown/mismatched scales cannot be
silently mixed. No amount is rescaled. Conflicting original currency/entity/unit
metadata prevents affected arithmetic while preserving the source fact.

Statement periods scope income/cash-flow fields in this schema. They never date
share points, maturity dates or an undated prior revenue period. Original raw
fact dates are preserved independently, including a market-cap observation that
differs from a balance-sheet date. A diagnostic ratio with mixed dates is not a
matched-period valuation. Unsupported schemas require another reviewed adapter;
do not rewrite original evidence to fit this one.

## Interpretation and coverage contract

- **Funding:** each maturity is compared separately with dated reported cash.
  The exact relation is less/equal/greater; cash minus principal is a nominal
  residual. Equality is not a shortfall, and neither a positive residual nor
  cash plus an undrawn revolver proves future available liquidity. Borrowing
  remains separate. Identical repeated rows are marked and never summed into
  additional obligations.
- **Dated changes:** share and revenue deltas are point-to-point arithmetic.
  Known dates yield an interval in days. Missing, reversed or conflicting timing
  never becomes an annual growth/dilution claim; no causal attribution is inferred.
- **Covenants:** the original clause is retained as uninterpreted text beside
  the leverage proxy. Contractual compliance, borrowing headroom and a formal
  threshold test remain unknown/unevaluated. The short clause cannot supply
  omitted definitions, adjustments or test conditions.
- **Cash and operations:** the cash bridge, capex residuals, margins and
  valuation diagnostics retain their operand identities and date scope. SBC
  economic proxies are separate from cash outflows; maintenance-only residuals
  are not FCFE. Recurring expenses are not automatically added back. Historical
  residuals are not a forecast of financing capacity.
  Raw numeric bridge equality remains separate from reconciliation: a
  `cfo_bridge_matches_reported` Boolean requires compatible source dimensions
  and matching explicit periods for every bridge operand and reported CFO.
  Missing or conflicting timing/scale leaves that match unresolved, even when
  the two displayed numbers coincide.
- **Business context:** descriptions are attributed source quotations. Customer
  concentration and peer margins are diagnostics, not a customer-loss forecast,
  proof of economic comparability or a competitive moat.
- **Valuation and monitoring:** this adapter does not construct a DCF or a
  discount-closure criterion. Monitoring entries are concrete research questions
  rendered from closed topic templates, not necessary/sufficient business
  conditions, trading triggers or permission to schedule actions. A separately
  computed terminal objective retains its own scope.

Every result displays all six business topics, including explicit unresolved
facts and the unevaluated valuation objective. `topic_coverage` means that these
sections were addressed; it does not certify complete research or correctness.
All original-source IDs and hashes remain in coverage, but a byte inventory is
not a claim that all source meanings or contradictions were resolved. Replaying
the report checks the declared schema and saved bytes, not those broader claims.
