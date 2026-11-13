# Objective-bound scenario evidence

Every terminal calculation now includes `diagnostic_objectives` and its generated
`report`, even without an optional claim contract. This projection keeps the
after-cost zero-return comparator, original rows, declared sensitivities and
derived one-parameter probes separate. It preserves every held assumption and
explicitly leaves DCF discount closure unavailable. Use those meanings in the
answer; the generated report is a projection of executed model diagnostics, not
source authentication, a plausibility forecast or validation of arbitrary prose.

Use `terminal_scenarios` with an optional `objective_evidence` contract when a
valuation question asks what must change, which assumptions are necessary, or
whether a proposed combination is sufficient for a named result. The helper
calculates outcomes and retains counterexample rows instead of interpreting a
favorable joint scenario as a proof about each assumption.

First name the result being tested. After-cost capital preservation, beating a
specified return hurdle, reaching a terminal price and exceeding a present-value
amount are different objectives. A quoted DCF opinion does not supply a terminal
price target or a recomputable DCF model. When the requested closure criterion is
not operationally defined, retain that missing criterion and label any numerical
comparators as diagnostics rather than claiming to have resolved the user goal.

The existing one-variable exit-multiple boundary remains useful for an analytic
zero-return threshold with other inputs fixed. This interface adds a different
capability: explicit finite joint-parameter evaluation, objective-specific claim
tests, and discrete frontiers that hold other declared axes fixed.

## Contract

Add this object to a normal terminal valuation request; original scenarios,
costs, dividends, reinvestment assumptions and model years remain unchanged:

```json
{
  "objective_evidence": {
    "domain": {
      "mode": "cartesian",
      "base_scenario_id": "central",
      "axes": {
        "terminal_ebit_margin": [0.1, 0.2],
        "exit_ev_to_ebit": [5, 10]
      }
    },
    "objectives": [
      {
        "id": "preserve_outlay",
        "role": "diagnostic_comparator",
        "measure": "net_total_return_fraction",
        "operator": ">=",
        "target": {
          "value": 0,
          "unit": "fraction",
          "valuation_basis": "holding_period_return",
          "horizon_years": 1
        }
      }
    ],
    "claims": [
      {
        "id": "test_joint_requirement",
        "objective_id": "preserve_outlay",
        "conditions": [
          {"parameter": "terminal_ebit_margin", "operator": ">=", "value": 0.2},
          {"parameter": "exit_ev_to_ebit", "operator": ">=", "value": 10}
        ]
      }
    ]
  }
}
```

Use the actual model horizon, not the example's one year. Roles are
`declared_objective` or `diagnostic_comparator`; the helper does not infer a goal
from a scenario name. Objectives and claims require unique IDs. Conditions within
one claim form an AND conjunction. Each condition is also tested separately.

Supported measures and target dimensions:

| Measure | Unit | Valuation basis | Additional binding |
|---|---|---|---|
| `net_total_return_fraction` | `fraction` | `holding_period_return` | `horizon_years` equals model years |
| `terminal_share_price` | `currency_per_share` | `terminal_price` | Matching currency and horizon |
| `present_value_of_modeled_distributions` | `currency_per_share` | `present_value` | Matching currency, horizon and `valued_at` equal to request `as_of` |

All numerical targets are explicit. A supplied benchmark return may be used as a
return threshold only at the matching horizon and return basis; no annualization,
cash reinvestment or horizon conversion occurs here. Distribution PV requires the
existing model's discount rate and complete dividend-timing contract. Missing PV
is unavailable, not zero or failure. Comparing modeled distribution PV to an
amount does not reconstruct an external DCF valuation.

An objective with `measure: "dcf_discount_closure"` and an explicit role records
`UNAVAILABLE_DCF_MODEL_NOT_EVALUATED`. This preserves the actual unresolved goal
alongside useful computed diagnostics. It requires a separate supported cash-flow
valuation model and closure criterion; the helper does not translate that goal
into zero return. All other objectives require a supported operator (`>=`, `>`,
`<=`, `<`, `==`, `!=`) and correctly typed numeric target.

## Domain and feasibility

`domain.mode: "supplied_scenarios"` evaluates only original scenario rows. A
relationship found in those rows is an association within the supplied sample.

`cartesian` evaluates every combination of the explicitly supplied axis values,
holding all other inputs at `base_scenario_id`. Axis names may be revenue growth,
terminal EBIT margin, tax rate, exit net debt, annual dilution, exit EV/EBIT or
cumulative dividends, using the existing scenario field names. Values must be
finite, numerically unique and valid for the underlying terminal model. At most
4,096 combinations are permitted. No automatic axis range, optimum, probability
or plausible valuation multiple is invented.

Crossing marginal values from separate scenarios does not prove the resulting
joint combinations are economically achievable. Label such an analysis as a
declared mathematical sensitivity. Funding and balance-sheet dependencies remain
unreconciled unless separately modeled. Exhaustive finite evaluation does not
cover the continuous parameter space or prove real-world necessity.

## Reading the evidence

For each objective, the output contains evaluated values, targets, residuals and
passing/failing/unavailable row IDs. Each row retains all terminal scenario
parameters. Follow a claim's counterexample IDs back to those rows before writing
a conclusion; claims are scoped to the named objective and domain.

- A necessity counterexample meets the objective while violating the proposed
  condition. A sufficiency counterexample meets the condition but fails the
  objective. Either is an explicit modeled witness, subject to domain feasibility.
- `HOLDS_ON_EVALUATED_FINITE_DOMAIN` applies only to the evaluated rows. It does
  not establish a general business requirement, and the output keeps
  `continuous_or_real_world_necessity_established` false.
- `NO_OBJECTIVE_SUCCESSES` and `NO_CONDITION_WITNESSES` avoid vacuous proofs.
  Missing objective values produce `UNDETERMINED` when they could affect the
  conclusion; they are never converted to unsuccessful observations.
- Discrete frontiers distinguish `axis_value` from objective `value`, retain
  held-axis values and adjacent outcome changes, and identify minimum/maximum
  **evaluated** passing values. `continuous_threshold` stays null. Do not infer
  interpolation or monotonicity from these endpoints.

An objective can have a sufficient modeled combination without every component
being necessary. Conversely, a finite domain can contain no success without
proving the objective impossible elsewhere. Report those results with the
specific objective and domain rather than promoting a sampled row to a universal
requirement.
