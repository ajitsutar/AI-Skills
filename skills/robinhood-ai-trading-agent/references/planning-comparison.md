# Declared alternatives and settlement/transfer paths

These offline helpers inherit `planning_alignment.finish`: explicit top-level currency and input role, input digest, advisory-only output, no source authentication claim, and no cross-currency conversion. Neither helper creates an order, approval condition, calendar lookup, broker availability claim, or external action.

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
