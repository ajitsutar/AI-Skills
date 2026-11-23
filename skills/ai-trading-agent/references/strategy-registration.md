# Typed strategy registration

For a new single-instrument long/cash research or paper design, follow the executable design section below. To replay the comparator, calendar and estimator registration format, run the original-record preflight with `--registered-design CHOICES.json --private-output OUTPUT`. For a caller that already has a structured selection, use the same `strategy_registration` object in a `strategy-answer` request. Supply `design_kind`, `answer_controls`, `design_terms` and `proposed_decision_rules` as in the strategy design workflow.

In registered mode, omit `benchmark`, `evaluation_window` and `development_validation_split` from `design_terms`. Omit `uncertainty` from `answer_controls`. Provide each of these choices once through `strategy_registration`. For example, a research caller with the selected record's start and end date fields can use this object. Replace the illustrative values with prespecified choices.

```json
{
  "benchmark": {
    "kind": "reference_series",
    "identifier": {"proposal": "total return index"},
    "currency": {"proposal": "USD"},
    "cash_return": {
      "convention": "annual_effective",
      "annual_fraction": {"proposal": 0.0},
      "day_count": "actual_365_fixed"
    }
  },
  "evaluation": {
    "start": {"record_pointer": "/evaluation_start"},
    "end": {"record_pointer": "/evaluation_end"}
  },
  "development_fraction": 0.65,
  "uncertainty": {
    "performance_rule": 0,
    "confidence": 0.95,
    "estimator": {"name": "circular_moving_block_percentile", "block_observations": 6, "replicates": 20000, "seed": 41}
  }
}
```

Each quoted currency, identifier, rate and ISO calendar date takes exactly one `record_pointer` relative to the selected record or one typed `proposal`. A supplied rate must point to a numeric annual fraction. A whole-document field outside the selected record cannot establish that input. For unavailable cash inputs use `{"convention":"unavailable"}` and treat affected comparisons as inconclusive. `simple_annual` and `annual_effective` rate conventions accept `actual_365_fixed` or `actual_360`. State how the benchmark and strategy apply the registered cash convention in the execution design. A `cash` benchmark omits the identifier. A `buy_and_hold` or `reference_series` benchmark requires one.

Link the selected directional performance rule to `measure="mean_paired_net_active_return"`, `units="return_fraction"` and `measurement_window="registered_evaluation"`. Use the arithmetic mean of matched strategy net returns minus matched comparator net returns. The estimator uses observations in the registered sample unit. Choose exactly one circular moving-block percentile estimator with its integer block length, resample count and seed, or `{"name":"newey_west_normal","lag_observations":4}`. Require the block length or lag to fit the declared minimum paired sample. Specify separate measures as secondary criteria. These typed methods describe a proposed bound and require actual paired observations to produce a result. For a scoped Newey–West design, omit `answer_controls.sample.rationale`. Register the observation floor and lag separately. At lag L, N observations provide N−L products for the longest lag. A chosen minimum for study eligibility can exceed the count needed to form those products. A finite and informative bound additionally depends on usable data, variance and precision. Put study-specific reasons such as desired regime coverage in the decision rule's measurement or inconclusive notes.

For a research contract, all development and validation observations must precede the inclusive evaluation dates. The development fraction divides that earlier sample chronologically. Purge crossing labels or trades. For a forward-paper protocol omit `development_fraction`. Actual calendar eligibility, source meaning, registration timing and prior use of observations require independent evidence.

The output receipt and verification report identify the registered or legacy scope. Other design fields still contain authored proposals. Verification replays their bytes. It does not establish external facts or verify every claim in those fields.

## Executable return and execution conventions

For a new single-instrument long/cash design use `research_preflight.py --request ORIGINAL.txt --source-root INPUTS --source DOCUMENT.json --scoped-design CHOICES.json --private-output NEW`. Keep the exact original user request. Build choices from the selected record and explicitly label additional proposals. Run `research_contracts.py schema` for editable research and forward examples under `strategy_answer.registered_request_schema.executable_design`. Put the applicable example inside `strategy_registration.economics`. The earlier registration format remains available for replay.

Register an available benchmark and cash convention, including an explicit sourced or proposed numeric annual rate and day count. A proposed zero is an assumption. Select the primary signal's fast/slow window pair from a record-relative pointer or a numeric pair proposal and the per-side cost in basis points from its selected field or a proposal. A directly supplied boolean state can instead use `{"kind":"binary_target","target_field":{"record_pointer":"/target"}}`. The long-entry budget fraction is in (0,1]. If the selected instrument, currency, signal, execution, financing or price basis conflicts with this supported book, retain the gap and use an appropriate prospective specification before evaluating it.

Omit `execution_convention` from design terms, and `initial_state`, `warmup`, `sample.minimum_events` and `sample.event_unit` from answer controls. The executable design generates them. Register at least two completed primary exposures and a separately justified paired observation floor. In forward mode include the proposed minimum on-time fill fraction and cap on mean adverse implementation shortfall; count every intended order, while preserving the separate unconditional journal reconciliation. Review the rendered answer and structured row before delivery.

In executable mode, bind the primary to the same selected-record signal field. A proposed primary uses the exact label `SMA(fast,slow)` with the registered integer windows, for example `SMA(4,12)`, or `binary_target(/field)` using the registered boolean field pointer. The executable signal and the primary decision must identify the same rule.

## Original response declarations

For a new structured strategy response, use the original request entry in research_preflight.py. It reads a response.json field list in the original request or in a neighboring PROTOCOL.txt when HASHES.json binds that protocol and PROMPT.txt. For another input layout, pass the original declaration with --response-contract at intake. Keep the resulting export intact. Delivery and final verification replay the retained declaration automatically, including when the caller supplies no flag. A missing field or different declaration prevents verified delivery.

Supply executable economics for a supported long/cash design. Register entry exposure, the common price and per-side cost convention for both books, and a cash convention. A forward-paper design also needs a minimum on-time filled fraction and a maximum adverse shortfall. Record unsupported strategies as incomplete and retain their research drafts. Historical artifact verification remains available.
