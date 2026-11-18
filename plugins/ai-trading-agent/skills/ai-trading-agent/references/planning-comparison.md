# Declared alternatives and settlement/transfer paths

These offline helpers inherit `planning_alignment.finish`: explicit top-level currency and input role, input digest, advisory-only output, no source authentication claim, and no cross-currency conversion. Neither helper creates an order, approval condition, calendar lookup, broker availability claim, or external action.

For a withdrawal or employer-stock comparison from a retained portfolio context,
run `planning.source_alternatives` with the common full-source projection contract
in [portfolio-projection.md](portfolio-projection.md). Compare the returned dated
weights and target drift before describing long-term effects. Present conditional
tax, liquidity and concentration tradeoffs. Preserving or maximizing a particular
issuer is not a user objective merely because the source supplies that holding.
Do not declare one sale uniquely optimal without explicit priorities.

The returned `proposal_contract` makes a conditional proposal valid without
nominating a favorite. When user priorities are absent, compare every funding
alternative with supported viability evidence and show conditional branches for
different priorities. Do not infer that observed liquidity, a lower tax estimate,
concentration reduction or preservation of an issuer is the user's highest
priority. Source order is presentation order; self-chosen objective weights are
not a default decision policy. Preserve unknown viability and missing metrics.
The contract selects no funder and creates no execution prerequisite. Explicit
user criteria can be evaluated separately with the existing comparison contract;
the source projection operation implements no preference optimizer.

The additive `allocation_direction_comparisons` records target-distance changes
between explicitly named alternatives on the shared projection convention. Use
absolute drift, not the sign of a trade or a rank among candidates, to describe
movement toward a target. No pair is automatically the starting baseline and no
per-asset direction establishes overall portfolio improvement. Unknown primary
denominators remain unresolved; identified-assets sensitivities stay separate.
See the final conditional-branch audit in [evidence-semantics.md](evidence-semantics.md).

`alternative_coverage_audit` inventories which held assets and sale quantities
appear in the supplied alternatives. Asymmetric sampling is not exclusive funding
capacity: compare common funding requirements across assets or preserve missing
information. Multi-trade combinations and isolated sale scenarios are distinct.
This audit does not invent an order, prove eligibility or choose a funder.

`source_context_evidence_inventory` retains analytical price/cost inputs and
optional source opening conventions with pointers and explicit roles. It does not
verify current quotes, broker fees or optional-scenario applicability. Use exact
roles when describing remaining unknowns; supplied assumptions are not absent
because actual execution is unknown.

Its `baseline_source_fields` retains supplied baseline fields with literal state,
value and source pointers. `owning_scope_pointer` identifies the baseline record;
`task_applicability: NOT_ESTABLISHED_BY_SOURCE_RECORD`,
`user_authorization_inferred: false` and `broker_requirement_inferred: false`
mean this inventory makes no authority or applicability inference.
`baseline_source_description` retains the source description literally; it does
not classify that description as proof of current policy. Determine the relevance
of each field from the user request and source scope before applying it.

For timing, run `planning.settlement_transfer_sweep`, not only a selected late sale.
It takes `currency`, `role`, `business_dates`, explicit `settlement_lag`,
`transfer_lag`, `spendable_deadline` and optional `same_day_transfer_assumption`
from the single-path contract below. Alternatively pass the whole `source`:
its `cash_conventions.test_business_dates` supplies the full date sequence, and a
caller-provided different/narrower calendar is rejected. Every listed sale date
on or before the deadline receives both same-day and next-listed-day initiation
paths. Keep earlier next-day-initiation paths in the proposal; compare their
conditions with later same-day-initiation paths. The sweep returns no preferred
date and never converts a conditional arrival into guaranteed broker availability.

The sweep additionally returns a deterministic `reference_path`: the earliest
supplied sale date whose `next_listed_day_initiation` path has modeled arrival
strictly before the deadline and is not explicitly excluded. It retains the full
conditional path and its cutoff/spendability conditions. This is a common date
accounting example that needs no same-settlement-day acceptance assumption, not a
selected sale date, recommended trade, available-cash claim or guaranteed arrival.
All other paths remain in `sale_dates`, and `selected_sale_date` stays null. If no
path meets that exact reference rule, `reference_path` is null. A null reference
does not create a trading restriction, extend the supplied calendar or select a
later same-day path automatically.

## Alternative comparison

`planning.alternative_comparison` / `alternative_comparison(document)` accepts:

- `criteria`: nonempty list of unique `id`, `metric`, `unit`, `basis`, and `direction` (`minimize` or `maximize`). Every criterion is part of the comparison. The basis must declare the same relevant valuation date, denominator, cost/tax convention and scenario across alternatives.
- `alternatives`: nonempty list of unique `id` and `values`, a map keyed by criterion ID. Numeric scalar values inherit the shared criterion dimensions. Null or absent values remain unknown. A dimensioned value record supplies `value`, `metric`, `unit`, and `basis`; absent or different metadata makes that cell noncomparable. Extra undeclared criterion IDs are rejected.

Values are finite Decimal comparisons. There are no weights, default objective priorities, inferred portfolio objectives, or selected winner. Top-level weights/priority/user_priority and per-criterion weights/priority are rejected because preference optimization is not implemented. Source order controls presentation only.

Pairwise dominance requires complete comparable values on every criterion, no worse values on all criteria, and a strictly better value on at least one. Equal vectors do not dominate each other. A missing or incompatible criterion prevents dominance for that pair, even if one alternative looks better on every known criterion. Known criterion advantages remain visible as conditional, criterion-local tradeoffs; they do not select a strategy.

`not_proven_dominated_ids` retains every candidate not dominated on a complete pairwise comparison. It is partitioned into `non_dominated_ids` (fully resolved comparisons) and `indeterminate_ids` (unknown/incomparable values or unresolved pairwise comparisons). If a new unknown alternative appears, otherwise strong candidates can also become indeterminate. This is deliberately conservative: no global winner is asserted in the presence of unresolved comparisons. A candidate proven dominated by one complete comparison remains dominated even if another comparison is unresolved. The source values, metadata, pairwise known advantages and unresolved criteria remain in the output.

## Settlement and transfer date paths

`planning.settlement_transfer_paths` / `settlement_transfer_paths(document)` accepts:

- `business_dates`: nonempty, strictly increasing unique ISO calendar dates explicitly supplied for the scenario. These are the complete sequence to use for this calculation; the helper does not verify their real business-day status or infer omitted dates.
- `sale_date`: a listed date; `settlement_lag` and `transfer_lag`: nonnegative integer counts of transitions in that list. A lag of zero means the same listed date.
- `spendable_deadline`: an ISO date; it need not be a listed date and may precede the sale.
- Optional `same_day_transfer_assumption`: `{accepted: true|false, basis: "supplied assumption or cutoff evidence"}`. It declares acceptance ordering, without authenticating the basis or parsing cutoff times.

The helper separates sale, settlement, transfer initiation and arrival. It enumerates initiation on the settlement date and on the next listed date, then advances each initiation by the transfer lag. Without an explicit same-day assumption, same-day initiation is only a possible path with unknown intraday acceptance. An affirmative assumption yields a conditional path; a negative assumption marks that path excluded by the declaration. The next-listed-day path is also conditional on initiation/acceptance and on the declared arrival being spendable. No path establishes actual broker or bank availability.

An arrival before, on or after the deadline date is labeled separately. An arrival on the deadline date explicitly retains unknown intraday ordering. Even an earlier modeled arrival is conditional; `guaranteed_spendable_by_deadline` is always false. Missing calendar coverage leaves the affected dates and deadline relation null; it never extends the supplied list, looks up holidays, substitutes calendar days, or fabricates a latest guaranteed sale. Dates calculated for an explicitly excluded path are counterfactual arithmetic and must not be presented as a feasible path.

Use the supplied source scenarios first. Extra example policies do not create approvals or execution conditions for an analytical proposal. Correct projected allocation denominators and explicit tax/cost conventions must be computed upstream and preserved in each metric basis before comparing alternatives.

The sweep's `sale_date_summaries` retains each timing mode's exact status and
dates. `calendar_uncovered_for_all_paths` and `calendar_coverage_mixed` distinguish
an uncovered whole date from mixed paths. One mode can have a known arrival on
the deadline with unknown intraday acceptance while another lacks calendar
coverage. Report both statuses; do not call that whole sale date uncovered.
`status_for_entire_date` stays null because the modes have separate assumptions.
Neither known calendar coverage nor an arrival date proves funds are spendable.
