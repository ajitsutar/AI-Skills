# Deterministic advisory allocation baseline

Use `allocation_policy.allocate(document)` when an allocation is requested, an
explicit ordered candidate set is available, and the user supplied no weights or
supported forecast/covariance optimizer request. This is the `planning.allocate`
document operation in the quant workbench. The standalone interface is:

```text
python scripts/allocation_policy.py retained-allocation-input.json
```

The default divides the full notional budget equally across the entire supplied
candidate set. Each selected name receives its equal fraction, with residual
cents assigned in the retained order. There is no invented portfolio count,
positive-score cutoff, score-weighted allocation, or assumed
relationship between a research score and expected return. Equal weighting is an
illustrative reproducible fallback, not evidence of optimal return, diversification
or a validated strategy.

This helper computes amounts only. Its data validation and research labels do not
permit or block live actions, create an execution approval workflow, or submit any
order. Native host and broker tools own any user-requested execution. No skill
execution gates are introduced.

## Selection and allocation contract

Selection precedence is explicit and fixed:

1. `user_selection`, in its exact supplied order.
2. Symbols in `user_weights`, in their exact supplied array order.
3. Every row of a `reviewed_selection`, preserving that exact set and order.
4. A prefix of the supplied source order when `requested_count` is supplied.
5. Every supplied row when no count is supplied.

Explicit user selections and weights override defaults. If both are supplied,
their sets must match; the selection array controls order. Conflicting explicit
sets are reported as invalid input rather than rewritten. The helper does not
re-rank rows, break score ties itself, replace rejected names, repair a research
queue, or invent names to meet a requested count. If the source contains fewer
names than requested, it returns every source name and reports the shortfall.
An explicit user or reviewed selection wins over a conflicting count, with
`count_conflict: true` and `requested_count_met: false`.

User weights are nonnegative decimal fractions whose sum must not exceed one.
They are never renormalized. A sum below one leaves unallocated notional budget;
zero-weight selected rows stay visible. Unsupported short/leverage weights are
reported as invalid input. This narrow arithmetic domain is not a trading policy.

For research/diagnostic queues, the complete result is always
`CONDITIONAL_RESEARCH_BASELINE`. Missing/incomplete primary review remains explicit
in each row and `missing_primary_review_symbols`. A `reviewed_selection` source
label alone does not fill missing row review. Even when every supplied selected
row declares complete review, `recommendation_validated` and
`source_authenticity_verified` remain false: this arithmetic does not audit the
underlying research. Coverage of a finite supplied set does not establish full
market/universe coverage.

## Version 1 document schema

The input is a JSON object with the fields below. Unrecognized top-level fields
are rejected to prevent misspelled selections/weights from silently using defaults.
Numbers used for money/weights must be decimal strings or JSON integers, not JSON
floats. Input, source rows, policy and result have explicit SHA-256 bindings.

| Field | Contract |
|---|---|
| `schema_version` | Required integer `1` |
| `currency` | Required explicit uppercase three-letter label; all nested currency fields must match. No FX is inferred. |
| `role` | Required `supplied_observation`, `hypothetical_scenario`, or `user_assumption` |
| `budget` | Required positive decimal string/integer, exactly representable in whole cents |
| `budget_basis` | Required `notional` or `fee_inclusive`; never inferred from a bare cash balance |
| `candidate_set` | Required source object described below |
| `mode` | Optional `portfolio` (documented default), or `alternative_single_stock` |
| `requested_count` | Optional positive integer or null; omission means no invented count |
| `user_selection` | Optional nonempty array of unique exact symbols present in the source |
| `user_weights` | Optional nonempty array of `{symbol, weight}` records, one per selected symbol |
| `horizon` | Optional retained JSON value; any requested duration/date/mode is kept unchanged |
| `order_details` | Optional object retained unchanged, separate from the advisory allocation amounts |
| `fees` | Optional retained array; this helper does not model even supplied fees |
| `constraints` | Optional retained object; a nonempty object leaves final sizing unresolved |
| `optimizer_inputs` | Optional retained object; a nonempty request routes to a separate implemented optimizer unless explicit user weights take precedence |

`candidate_set` contains:

| Field | Contract |
|---|---|
| `kind` | Required `explicit_candidates`, `diagnostic_queue`, or `reviewed_selection` |
| `source_id` | Required stable reference chosen by the caller for the retained source |
| `declared_count` | Required integer exactly equal to the number of `rows` |
| `rows` | Required nonempty ordered array of candidate records |
| `rows_sha256` | Optional canonical hash checked against the actual supplied rows |
| `source_sha256` | Optional lowercase 64-character SHA-256 of the upstream retained source; preserved and syntax-checked, not authenticated or recomputed without source bytes |
| `universe_count` | Optional integer at least as large as the supplied row count |
| `coverage_complete` | Optional upstream coverage declaration. `true` requires an explicit universe count, which may exceed the selected row count. It is retained but never verified by this allocation helper. |

Each row requires `symbol`, `issuer_id` and `currency`. Symbols and issuer IDs must
be nonempty exact strings without surrounding whitespace. Repeated symbols or
issuer IDs, including case variants, are rejected rather than merged. Caller
supplied issuer IDs are necessary to catch multiple share classes; distinct ID
strings alone are not proof of distinct real issuers. Perform the relevant issuer
resolution upstream. There is no automatic share-class substitution.

A row may have `primary_review_status`: `complete`, `incomplete`, `not_reviewed`,
`unknown`, or null/omitted. Absence remains null in the output. Optional per-row
`order_details` are retained independently of global order details. Extra source
row fields, such as scores, ranks and evidence metadata, are preserved in
`retained_input` and covered by the source-row hash, but do not affect allocation.

An upstream screen can cover an entire declared universe while its final selection
contains only a subset. `coverage_complete` describes that upstream declaration,
not equality between universe size and selected row count. `coverage_verified`
always remains false here; no coverage label replaces a membership/data audit.

The caller must bind the actual upstream source to these fields. For a handoff
that has `selected_symbols`, create a `reviewed_selection` from exactly that
ordered selected set, retaining its source hash and actual review statuses. If
there are only `research_candidates`/a diagnostic queue and incomplete review,
use `diagnostic_queue`. Never relabel a queue as a reviewed selection to produce
a more authoritative-looking output.

```json
{
  "schema_version": 1,
  "currency": "USD",
  "role": "hypothetical_scenario",
  "budget": "500.00",
  "budget_basis": "notional",
  "horizon": {"value": "18", "unit": "months", "mode": "comparison"},
  "order_details": {"order_basis": "native_dollar", "order_type": "market"},
  "candidate_set": {
    "kind": "diagnostic_queue",
    "source_id": "fictional-retained-queue",
    "declared_count": 3,
    "rows": [
      {"symbol": "C", "issuer_id": "issuer-c", "currency": "USD"},
      {"symbol": "A", "issuer_id": "issuer-a", "currency": "USD"},
      {"symbol": "B", "issuer_id": "issuer-b", "currency": "USD"}
    ]
  }
}
```

This example returns C 166.67, A 166.67, B 166.66, as a conditional research
baseline with missing primary review for all three. The symbols are fictional
identifiers; this example supplies no market research.

## Cents, order details and separate alternatives

Money arithmetic uses `Decimal` and a calculation-local precision derived from
the input coefficients/exponents. It does not depend on a caller's Decimal
precision. Equal allocations divide integer budget cents, assigning residual
cents to the earliest selected rows. Explicit weights use largest remainders:
floor each exact weighted amount in cents; floor their summed exact amount; then
assign the residual cents to descending fractional remainders, breaking equal
remainders by explicit selected order. No alphabetic or score tie rule is invented.
The summed amount never exceeds the budget or the floored requested weighted
total. Realized cent amounts can differ slightly from exact target weights, which
are separately retained. No tiny allocation is silently dropped to meet an
invented broker minimum.

Two-decimal denomination is an advisory reporting convention in this version,
not a claim about a currency's legal minor unit or a broker's order increments.
The helper does not validate a real currency registry, assume fractional share
eligibility, estimate shares from a price, or replace a native-dollar instruction
with a rounded quantity order. Unsupported currency/precision/broker requirements
remain outside this calculation. No FX or conversion between currencies is used.
Global and per-row order details remain unchanged; an advisory notional is not a
replacement for an explicitly supplied amount, quantity, order type or limit.

`alternative_single_stock` is a separate, explicitly selected mode. Each row is a
mutually exclusive scenario receiving one full budget. These amounts must never
be summed into one portfolio: portfolio totals are null, while
`budget_per_alternative` and separate scenario IDs are provided. User portfolio
weights conflict with this full-budget alternative mode and are not reinterpreted.

## Unresolved costs, constraints and calibration

For a `notional` budget without unsupported constraints, `advisory_cash_amount`
is the before-fee allocation, and `allocated_notional_total` conserves that budget
unless user weights explicitly retain cash. The all-in debit, available buying
power and `cash_affordable` remain null. This is not fee-inclusive affordability.
Neither missing fees nor an empty fee list establishes zero real transaction costs.

For a `fee_inclusive` budget, the same allocation is shown only as
`reference_notional_before_fees`; `advisory_cash_amount` and the aggregate
`allocated_notional_total` remain null. `sizing_status` is `SIZING_UNRESOLVED`,
and `FEE_INCLUSIVE_NOTIONAL_SIZING_UNRESOLVED` is explicit. Reference notionals
that sum to the cash cap are not a claim that fees fit inside it. Supplied fees are
retained but not applied. The separate `planning.trade_costs` contract can model
explicit supported cost units with the required inputs; no fees or broker rules
are borrowed automatically from other helpers.

Nonempty constraints likewise preserve the reference split while leaving final
amounts unresolved; no concentration, liquidity, share increment, tax, borrowing
or affordability feasibility is claimed. Supplying a nonempty `optimizer_inputs`
object without user weights produces `OPTIMIZER_INPUTS_REQUIRE_SEPARATE_OPERATION`
and null target weights/amounts. This helper does not decide that such inputs are
calibrated or supported: route them to the implemented optimizer and retain its
actual outcome. Unsupported or partial forecast observations may be retained as
source row metadata but must not be presented as a calibrated optimizer request.
Explicit user weights remain authoritative if also supplied.

`expected_return` and `performance_claim` are always null; covariance/returns are
not estimated, and no optimization is performed. An arbitrary horizon is retained
without changing the equal-notional arithmetic, forcing an exit or claiming a
strategy works over that horizon.

## Output and replay

Output includes schema version, policy ID/version/content/hash, normalized-source
implementation hash, input hash, candidate-row hash and a full `retained_input`.
It lists selection/weighting provenance, documented defaults actually used, counts,
review status, unresolved items, individual amounts and mode-specific totals.
`result_sha256` hashes the canonical result before adding that checksum field.
Canonical JSON uses sorted keys, compact separators, UTF-8, preserved Unicode and
no NaN. Changing source order changes the input/source hashes and, for residual
ties, which symbols receive the last cents. Changing source order must be a
retained input edit, never a hidden re-ranking.

Workbench usage nests this document under a job's `inputs.document`. Keep the
workbench contract currency and intended horizon consistent with the retained
allocation document. Existing frozen research/quant bundles remain immutable;
create a new input/result for the new policy implementation. A checksum establishes
replay identity, not source truth or investment performance.
