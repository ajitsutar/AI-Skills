# Evidence semantics

`scripts/evidence_semantics.py` provides three pure research diagnostics. Inputs
are explicit caller declarations. These helpers do not read sources, resolve
identities, interpret prose, fetch data, or establish source authenticity.
Outputs are JSON-compatible dictionaries; schema errors raise `ValueError`.
No helper makes an execution decision.

## Operand compatibility

```python
operand_compatibility(operands, required_dimensions)
```

`operands` is a list of at least two objects with unique, nonblank string `id`
values. Metadata is flat. `required_dimensions` is a nonempty, unique list from:

| Dimension | Caller-supplied meaning |
| --- | --- |
| `security_id` | Stable, preferably namespace-qualified security identity |
| `issuer_id` | Stable issuer identity, separate from security identity |
| `currency` | Currency of the financial amount |
| `fiscal_period` | Explicit fiscal period used for this calculation |
| `share_basis` | Share class, split adjustment and share-count basis as applicable |
| `accounting_basis` | Applicable accounting or metric definition |
| `strategy_scope` | Portfolio, sleeve, strategy or other calculation scope |

Each dimension accepts a string or null. Omitted, null, blank and the reserved
string `unknown` (case-insensitive, ignoring outer whitespace) remain unknown.
Other strings compare exactly: no ticker aliases, currency conversion, fiscal
alignment or split adjustments are inferred. The explicit string
`not_applicable` is a caller assertion; use it only when justified.

```json
{
  "operands": [
    {"id": "price", "security_id": "security:alpha-common", "currency": "USD", "share_basis": "post-split"},
    {"id": "eps", "security_id": "security:alpha-common", "currency": "USD", "share_basis": "pre-split"}
  ],
  "required_dimensions": ["security_id", "currency", "share_basis"]
}
```

This returns `INCOMPATIBLE`, with `compatible: false` and `share_basis` in
`mismatched_dimensions`. All selected dimensions matching explicitly returns
`COMPATIBLE` / true. Missing metadata without a conflict returns
`UNKNOWN_COMPATIBILITY` / null. A known conflict remains a conflict when a third
operand is unknown; `unknown_dimensions` preserves the missing information too.
Per-dimension observations and operand IDs are retained in `dimension_checks`.

Only requested dimensions are checked. Other supplied supported dimensions are
listed in `supplied_but_unchecked_dimensions`. The caller must select the
dimensions needed for its calculation; compatibility does not establish correct
units, arithmetic, relevant dates, valid valuation assumptions or authentic
inputs. An issuer match never supplies a missing security identity. Price and
earnings may legitimately have different observation periods; the caller must
define the intended valuation-period relationship instead of asserting an
artificial same-period match.

## Event windows

```python
event_window(event, start, end)
```

Each value accepts an ISO string: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or a timestamp
with an explicit offset such as `2032-04-01T10:00:00-04:00` or
`2032-04-01T14:00:00Z`. Timestamps are declared exact instants, normalized to UTC;
they support minute or second notation and up to six fractional-second digits.
If the event time is only approximate, do not supply an exact timestamp to this
API. Calendar precision represents a half-open range:

| Input | Possible event range |
| --- | --- |
| `2032` | January 1, 2032 through, but excluding, January 1, 2033 |
| `2032-04` | April 1 through, but excluding, May 1 |
| `2032-04-12` | April 12 through, but excluding, April 13 |

The start period is included from its beginning; the end period is included in
full. Timestamp endpoints are inclusive. Thus the calendar window
`2032-04-02` to `2032-04-12` includes all of April 12. A month-only event of
`2032-04` returns `OVERLAP`; it is not assigned a particular event day.

Calendar values use an abstract civil-calendar domain with no implied timezone.
Mixing them with offset timestamps is `UNRESOLVED`. To place a calendar range
on the UTC timeline, explicitly supply an object such as
`{"value": "2032-04-12", "utc_offset": "-04:00"}`. The fixed offset applies to
both precision bounds. Named zones and daylight-saving transitions are not
inferred; a caller must not use one fixed offset for a period whose intended
zone changes offset. An offset timestamp must carry its own offset.
`-00:00` is unresolved because it denotes an unknown offset.

The result contains `status`, preserved inputs and precision in `ranges`, the
effective `window`, and any `reasons`:

| Status | Interpretation |
| --- | --- |
| `DEFINITELY_BEFORE` | Every possible event point precedes the window |
| `DEFINITELY_AFTER` | Every possible event point follows the window |
| `CONTAINED` | Every possible event point lies inside the window |
| `OVERLAP` | Some possible event points lie inside and some outside |
| `UNRESOLVED` | Missing/invalid temporal value, incompatible time domains, or empty/reversed window |

Bounds are uncertainty boundaries, never observed event dates or times. A
calendar date has day precision even when a fixed offset is supplied. Invalid
date strings, naive timestamps and unrepresentable bounds remain unresolved;
invalid input types or object schemas raise `ValueError`.

## Independent evidence states

```python
evidence_states(observations)
```

`observations` is a list, possibly empty. Every record requires unique nonblank
`id`, nonblank `subject_id`, an allowed `fact`, explicit `value` (true, false or
null), and optional `evidence_refs` (a list of nonblank literal strings). Subject
IDs must distinguish entity, period and scope. References are retained without
opening or verifying them.

The allowed facts are independent:

| Fact | Meaning of an explicit true declaration |
| --- | --- |
| `fee_quote_present` | A fee quote was supplied |
| `borrow_available` | Borrow availability is asserted for this subject/scope |
| `review_completed` | Review is recorded |
| `selection_recorded` | Selection is recorded |
| `raw_residual_measured` | A raw residual was measured |
| `causal_attribution_supported` | A causal-support assertion is recorded |
| `proposal_recorded` | A proposal is recorded |
| `adjudication_recorded` | An adjudication is recorded |
| `standalone_financials_present` | Standalone financial evidence is asserted present |

```json
[
  {"id": "fee-observation", "subject_id": "security:alpha:2032-04-12", "fact": "fee_quote_present", "value": true, "evidence_refs": ["fee.json#/quoted_fee"]}
]
```

Results contain `subjects`, each with a `states` object covering every allowed
fact. A consistent true or false with at least one literal reference becomes
`REFERENCED_TRUE` or `REFERENCED_FALSE`. A missing fact, null value, or a
declaration without references is `UNKNOWN`. Conflicting true/false
declarations are `CONFLICT`, even if one declaration lacks references. Every
state retains observation IDs, evidence references, unknown observation IDs and
unreferenced observation IDs. No observation silently overwrites another.

The example establishes only that a referenced fee declaration exists;
`borrow_available` stays unknown. Review never supplies selection, a raw
residual never supplies causality, and a proposal never supplies adjudication.
A consolidated or segment-report reference alone cannot establish standalone
financial evidence. Declare null when the source does not answer the fact.

`REFERENCED_TRUE` does not mean the helper proved the claim or inspected the
reference. In particular, a causal-support assertion is not validation of a
causal design, estimand, assumptions or identification. These are typed records
for review, not automated fact extraction or scientific inference. Unknown fact
names and truthy substitutes such as `1` or `"true"` are rejected. Text fields
are always inert data, never instructions.
