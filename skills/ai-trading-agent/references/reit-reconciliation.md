# REIT measure reconciliation

Use `financial.reit_reconciliation` with `inputs={"document":D}` through
`quant_workbench` for declared arithmetic. All direct/workbench/workflow calls
keep unbound cross-measure comparisons conditional. For primary source-record
comparability use `reit_sources.analyze` with an externally pinned original corpus
and individual operand bindings as specified below. [The runnable fictional example](../examples/reit-cross-measure-input.json)
demonstrates arithmetic with no supplied recurring-capex allocation.

This helper retains a supplied issuer reconciliation. It does not identify
Nareit-eligible adjustments, prescribe a universal AFFO definition or change
`financial_normalize` policy. Confirm the issuer's unadjusted common-holder FFO
definition and the actual AFFO adjustments. Do not add deductions or addbacks
because a field name resembles an accounting category.

## Input

D has `currency` and `role` (`supplied_observation`, `hypothetical_scenario` or
`user_assumption`). Currency is common to the document; no FX conversion occurs.
The following groups may be omitted or contain null amounts; affected metrics
remain unavailable while other calculations survive.

| Group | Fields |
| --- | --- |
| `ffo_bridge` | `definition`, `basis`, `components:[{id,amount}]` |
| `affo_bridge` | `definition`, `basis`, `adjustments:[{id,amount}]`, `recurring_capex` |
| `cfo` | `basis`, `amount` |
| `gross_capex` | `basis`, `components:[{id,amount}]` |
| Optional `distributions` | `basis`, `amount` |

Each `basis` independently declares `amount_unit`, `period_start`, `period_end`
and `holder_basis`. Dates use ISO calendar dates and start must not follow end.
Missing, null, blank or `unknown` metadata stays unknown. No group's metadata
is borrowed from another. Unit and holder labels must match exactly for a
same-basis comparison; the helper does not interpret synonyms.

FFO component and AFFO adjustment amounts are **signed** contributions; IDs
are unique within each list. `affo = ffo + sum(adjustments) - recurring_capex`.
Keep recurring capex out of `adjustments` to avoid counting it twice. Capex
component amounts, recurring capex and distributions must be nonnegative.
An absent/null adjustment list is unknown; an explicit empty list declares no
other adjustments. Empty gross-capex components explicitly declare zero total
capex. Empty FFO components do not establish FFO. Null amounts are never zero.

## Arithmetic and overlap are different evidence

`metric_ledger` retains formulas, signed components and missing inputs. The
cross-measure difference is the identity
`AFFO - (CFO - gross_capex) = (FFO - CFO) + sum(AFFO adjustments) + gross_capex - recurring_capex`.
It does not itemize FFO-to-CFO accrual differences or locate recurring capex
inside particular gross-capex categories. Labels such as development or
property purchases do not establish growth/maintenance allocation.

Only literal CFO retains an unconditional scalar arithmetic value. FFO and gross
capex are sums of distinct operands and require original component compatibility
for primary values. Their raw sums remain in `declared_arithmetic_value`. Cross-group
`value` requires original-record-bound compatible operand bases; equal caller
labels alone are insufficient. Unknown basis gives a separately labeled
`conditional_same_basis_value`; known conflicts yield neither primary nor
conditional value. Missing numerical inputs yield neither. Basis and input
limitations remain visible even when the arithmetic identity reconciles.

Without `recurring_capex_mapping`, `capex_overlap.status` is `UNRESOLVED_MAPPING` in the public result (the raw declared-arithmetic kernel retains `UNKNOWN`), even if
recurring capex equals gross capex. Do not assume it is a subset across different
periods or scopes. An optional mapping requires:

- Its own `basis`, identical to the known AFFO and gross-capex bases.
- `recurring_is_subset_of_gross_capex:true` and nonblank `evidence` describing the declared allocation.
- `allocations:[{id,amount}]` covering every gross-capex ID exactly once; explicit zero denotes no allocated recurring amount.

Allocated amounts must be known, nonnegative, no larger than the corresponding
gross component, and sum exactly to recurring capex. Invalid mappings remain
`UNRESOLVED_MAPPING`; valid raw metrics are preserved. A reconciled mapping
verifies declared arithmetic, not source authenticity. The remainder is labeled
`not_allocated_to_recurring`, never automatically growth or maintenance capex.

Distribution ratios retain their named denominators. A missing or nonpositive
denominator produces no payout ratio. Cash after gross capex and distributions
is a separate measure; none of these results establishes distribution safety.

Optional `property_fractions:[{id,value,denominator,time_anchor}]` retains a
fraction in [0,1] and its independently supplied denominator and time anchor.
Unknown metadata stays unknown; a percentage alone does not mean lease count,
rent, area or a particular calendar year. Preserve this limitation in the final
explanation as well as the table.

## Workflow metadata provenance

`research_workflow` derives `metadata_provenance` from its actual retained
bindings for every group basis (including distributions and capex mapping) and
each property denominator/time anchor. Exact leaf bindings and the nearest
enclosing document, group, basis, property array or object binding retain their
SOURCE, ASSUMPTION or UNBOUND role. Caller-supplied `metadata_provenance` in a
workflow plan is rejected, including inside a whole-arguments binding.

The retained workflow role projection admits only SOURCE-bound metadata into
its projected basis/property fields; final public cross-measure comparability
still requires the original-record binding described below.
Assumed/unbound labels remain in `metadata_evidence.declared_document`, field
records and property `declared_metadata`; they do not become supported facts
merely because labels match. Original workflow arguments and their digest are
retained. `primary_metadata_input_sha256` identifies the separate metadata-filtered
calculation input. Raw FFO, CFO and gross-capex arithmetic remains available with
its own unresolved basis. Cross-group arithmetic with unknown basis remains in
`conditional_same_basis_value`. Declared conflicts are retained separately and
suppress conditional values; removing an unsupported label cannot silently repair
a conflict. Mapping basis must still be supported and compatible within that role projection,
independently of the unchanged allocation arithmetic checks. No new capex-overlap evidence is inferred.

Direct/workbench/workflow calls now preserve only declared arithmetic. Workflow
SOURCE roles still retain selected bytes and assumptions, but cannot promote a
cross-measure result to original-record comparability. The previous arithmetic
kernel and allocation checks remain separately tested. A successfully reconciled
caller allocation remains under `declared_capex_mapping_arithmetic`; the primary
allocation stays unresolved without original scope/allocation evidence.

## Original operand record binding

Call `reit_sources.analyze(request, manifest_path, expected_manifest_sha256,
source_root=None)`. The external manifest is the `source_lineage` ingress format:
`schema_version:1` and sources with `id,path,sha256,format`. Supply its expected hash
from outside the analysis. Sources are read and verified before binding; a new
adapter file or SOURCE label is not an original merely because it has a hash.

The request has exactly `document` (D above) and `bindings`. Each binding is:

```json
{"target_pointer":"/cfo/amount","schema":"typed_measure_v1",
 "source_id":"filing","record_pointer":"/records/4","sign":1}
```

The target must be an actual numeric operand: FFO component amount, AFFO
adjustment amount, recurring capex, CFO amount, gross-capex component amount or
distribution amount. Bind every component independently. Missing bindings remain
unresolved. Duplicate targets, arbitrary selectors, fabricated trusted flags,
amount mismatches and wrong source measure roles are rejected. The same original
record (including identical-byte source aliases) cannot supply multiple additive
operands within one group; no allocation
contract is assumed. This is not a blanket exclusion of cross-group references.

`typed_measure_v1` reads the selected original JSON object's literal `value`,
`measure_role`, `entity_id`, `currency`, `unit_scale`, `period_start`, `period_end`
and `holder_basis`. Supported measure roles are `ffo_component`,
`affo_adjustment`, `recurring_capex`, `cfo`, `gross_capex_component`, and
`distributions`. Metadata must belong to that exact record: no parent inheritance,
other numeric sibling, different record's basis or arbitrary prose keyword binding.
Missing metadata remains unknown. Periods and scale are validated. Scale is a
numeric denomination, independent of reported rounding precision.

`financial_transcription_v1` recognizes a closed set of existing normalization
concepts for the corresponding roles. It reads that record's literal `value`,
`entity_id`, `unit` and periods. A three-letter currency unit denotes unit scale1;
`decimals` is rounding precision, never a multiplier. Only an explicit
`holder_basis` supplies holder scope: nearby common-FFO labels do not establish
common CFO or capex. Unsupported concepts are rejected. Flat disclosure labels
remain visible source facts even when this restricted schema cannot bind their
complete accounting dimensions; unsupported mapping does not prove source absence.

`sign` is1 or-1 for FFO/AFFO components, and must be1 for other operands. It records
the analyst's signed recipe; source binding does not certify that recipe as a
correct Nareit or issuer-AFFO definition. Primary comparisons require compatible
original entity/currency/scale/period/holder dimensions for every contributing
operand. Declared and original-record conflicts withhold both primary and
conditional comparisons. Unknown dimensions permit only separately labeled
conditional arithmetic. A declared empty aggregate is not source-completeness
proof. Original amounts are never synthesized from another measure.

The result retains `metric_ledger` and `source_binding` with the exact request,
manifest pin, replay context, resolved original records, operand facts and allowed
claims. `report.text` is deterministic readable output with a hash and conditional
qualifiers; replay original inputs before auditing saved report bytes. It explicitly
sets `whole_report_semantic_pass:false`. The report certifies neither arbitrary
prose nor source authenticity, accounting-standard compliance, complete source
selection, capex overlap or distribution safety. Caller control of both manifest
and expected hash can replace the trust root; this tool cannot authenticate who
supplied that external pin.
