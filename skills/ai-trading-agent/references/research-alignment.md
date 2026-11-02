# Keep the research request, calculation and explanation aligned

Use the [source-bound workflow](source-bound-workflow.md) to compose the operations
below into one retained plan and generated report. Inspect unused source fields
and every declared requirement before explaining the result.

Use this workflow for substantive research with supplied data or comparisons.
It addresses three separate questions: did the agent use the requested inputs,
did the implemented calculation run, and does the answer describe its result?
Agreement on one question does not establish the others. These are research
receipts, never requirements for broker execution.

## Bind the actual request

Read the full current request and the relevant supplied records. Preserve explicit
user choices before applying optional helper defaults. Separate actual account
observations, the user's mandate, hypothetical scenarios and sample configurations.
A sample no-sales setting is not a standing restriction unless the user adopts it.
Record which supplied fields were selected, unused, conflicting or unresolved.
Do not call a value missing merely because it appears in prose or another allowed
file instead of the first JSON object inspected.

Use `research_contracts.py schema` for the supported receipt contracts, then:

```text
python scripts/research_contracts.py bind-request REQUEST.json --source-root SOURCES --private-output NEW_DIRECTORY
python scripts/research_contracts.py inventory-evidence REQUEST.json --source-root SOURCES --private-output NEW_DIRECTORY
```

Source references use an explicit local allowlist, file SHA-256 and JSON pointer.
Attach dates, currency, accounting period and share basis to the same identified
record as the value. A publication date from a different series is not that value's
publication date. The binding report exposes selected roles, record conflicts and
unused input pointers; inspect them against the user's actual request. It cannot
automatically establish which interpretation the user intended.

Evidence inventory distinguishes bytes present from bytes missing, declared
classification from unknown classification, and publication/availability from
retrieval. Unknown security type is not an established exclusion. A cached dated
membership file does not establish unchanged current membership. Missing acquisition
receipts do not establish zero acquisition failures. An edited input with an
unchanged source reference is an input edit, not an authenticated restatement.
Use the inventory's supported source, freshness and report checks when requested;
listing their names or copying hashes is not executing them.

## Choose the implemented operation without changing the question

Inspect `quant_workbench.py operations` for exact arguments. Prepare and run supported
numerical work through `research_workflow.py`, retaining its original request,
resolved parameters, bundle, facts and report. Its `summary` verifies the complete
directory before projecting claims. The lower-level `quant_report.py` remains
available for an already bound request. Use the relevant interfaces below.
Nested document fields and calculation limits are described in
[alignment calculation contracts](alignment-calculations.md); complete fictional
jobs are included in `examples/fictional-quant-campaign.json`.

| Request | Shared calculation or receipt |
|---|---|
| Raw financial observations without a normalization envelope | `data.normalize_flows`; explicit reviewed mappings, source bytes and precision, then the existing normalizer; [contract](flow-normalization.md) |
| After-cost affordability, trade fees, dated cash, vesting, portfolio reconciliation, session P&L | `planning_alignment.py` operations in the workbench |
| Candidate-set allocation without supplied weights or optimizer inputs | `planning.allocate`; equal notionals, explicit source order/count, separate full-budget alternatives |
| Cash-budget alternatives and selected portfolio affordability | `planning.budget_sizing`; retain quantity, entry cost, debit and residual for each explicit increment |
| Quote observations versus modeled one-way slippage | `planning.friction_context`; preserve reference basis and overlapping-cost declarations |
| Supplied concentration, fund coverage and dollar-volume context | `planning.allocation_context`; source-bound facts with fixed denominator and explicit unknowns |
| Missing account state, pending amounts, targets and ceilings | `planning.input_roles`; preserve declarations and compare only compatible metrics |
| Sleeve comparison without supplied weights | `planning.reference_comparison`; capability/unknown comparison first, explicit unit exposure second; no invented shock grid or allocation |
| Future holdings or post-withdrawal weights | `planning.dated_projection`; account for supplied flows and use the same projected denominator |
| Conditional sale taxes | `planning.tax_sensitivity`; explicit basis/rate/cost treatment, no inferred loss credit or payment |
| Competing objectives without supplied weights | `planning.alternative_comparison`; complete-criteria dominance, unknowns and conditional tradeoffs |
| Sale-to-withdrawal date planning | `planning.settlement_transfer_paths`; distinguish settlement, initiation and arrival; no invented cutoffs |
| CFO/owner-cash bridges, reinvestment, acquisition cash, terminal scenarios, corporate actions | `financial_alignment.py` operations in the workbench |
| Dual fast/slow moving-average crossover, long/cash | `strategy_research.py` dual-SMA operations, with its own strategy identity |
| Supported three-bar opening-range baseline | `strategy_research.py` wrapper around the existing `strategy_lab.py` baseline |
| Forward-study admissibility and implementation evidence | `forward_evidence.py` operations in the workbench |
| Covariance changes, explicit expiry-hedge scenarios, typed inequalities/comparisons | `analysis_checks.py` operations in the workbench |
| Fixed exit versus flexible review | `research_contracts.py route-horizon` |
| Required ranking profile and implementation identity | `research_contracts.py audit-ranking`, followed by actual scorer/replay |
| Comparable analyst cohorts and supplemental evidence | `analyst_report.py`, using the existing cohort rules |
| Exact native-dollar/share/order-type/routing preservation | Private `handoff_report.py`; advisory only |

Keep fixed dates distinct from flexible comparison dates. A flexible review date
does not become a previous-session forced sale or acquire an exit buffer. Event
coverage ends where the evidence ends; report the remaining interval as unknown.
Label a chosen latest-entry date as a planning assumption unless a supplied rule
actually derives it. Record arbitrary holding periods without manufacturing future
events, terminal prices or forecasts.

Keep supported strategy identities distinct. Price crossing one moving average,
two moving averages crossing, and an opening-range breakout are different rules.
The dual-SMA implementation uses completed history, subsequent opens, explicit
delay and long/cash positions. Retain both entry and exit costs, marked equity,
pending orders beyond the available data, and the terminal-position policy.
Changing several parameters together cannot isolate a cost or delay effect.

Keep observed forward data separate from synthetic rows and retrospective tests.
Rows before the declared study window or with outcomes available before they occur
do not become forward observations because they were newly authored. Matching
descriptions are not proof of matching implementation or fills. The forward
admissibility report checks declarations and retained evidence, not authenticity.

## Preserve accounting meaning

Use both entry and exit costs with their supplied units. Per-share, per-order,
per-side and round-trip amounts are not interchangeable. If a source leaves the
unit ambiguous, preserve an unresolved primary amount and label any alternative
interpretations as sensitivities; do not promote one invented unit into a default.
State whether affordability
is before or after modeled costs; a broker's actual market debit is a separate fact.
For a budget-sized portfolio or alternative, compute after-cost quantities rather
than leaving a before-fee quantity labeled affordable after its debit exceeds the
budget. Report existing issuer, sector, industry and volume facts from the same
selected rows. Missing external diligence does not erase adverse facts already
supplied. See [portfolio decision calculations](portfolio-decision-calculations.md)
for composable contracts; findings remain advisory.
Withdrawals occur at their supplied cash-demand times. Settlement applies to trade
proceeds, not automatically to a withdrawal. Future vested shares are stock until
the relevant vest, sale and cash-availability events exist.

Reconcile declared account equity with identified positions and explicit cash.
Report any unexplained residual, and label percentages against both declared
equity and identified assets when useful. Do not replace one denominator with the
other silently. Daily P&L needs prior/session marks and dated flows; lifetime cost
basis alone cannot supply it. A balance reconciliation does not establish buying
power. Constraints on sales or one rebalance do not prove concentration is permanent;
contributions, relative prices and subsequent rebalances can change it.

Separate reported CFO minus all capex, maintenance-capex cash, cash after acquisitions
and an explicit SBC economic deduction. An earnings addback is not automatically a
cash addback: establish its amount, cash timing and tax treatment or leave that cash
adjustment unresolved. Model requested working capital and growth reinvestment.
Separate terminal share price, accumulated dividends, costs, total return and
discounted present value. Partial synergy cash over a few years is not total deal
NPV without the rest of the acquisition cash flows and terminal economics.

## Explain only what the result establishes

Use retained facts for numerical claims, with the same units, denominator and
period. Keep unknown frequency unknown; a holding horizon does not make an undated
return series daily. Preserve nested outcomes such as infeasibility and ambiguous
XIRR, not just an outer successful computation. Append custom facts to the full
built-in set. Old retained bundles keep their old implementation provenance; a
recognized historical schema allows interpretation, not a claim of current replay.

Use `analysis.compare_claim` for an explicitly typed numeric comparison when it
helps. Numeric equality uses declared tolerances; an inequality such as below a
covenant boundary retains its exact boundary. The comparator reports missing or
incompatible metadata instead of silently comparing unlike quantities. It is not
a general prose checker.

Do not turn relative valuation or complete inputs into proof of intrinsic value,
growth, buy eligibility or a Strong Buy. Preserve the requested ranking profile and
queue. Review whether the supplied quality/momentum inputs are actually sufficient
before claiming they are unavailable. Do not use an unsupported proxy as another
metric, such as calling income divided by assets-minus-debt return on equity.

Provider aggregates and a recomputed analyst cohort are distinct. Show any residual
difference; differing composition is a hypothesis until actual constituent vintages
and methods explain it. Biography, conflicts and published corrections are evidence
records, distinct from changes to forecasts or ratings. Do not pool target horizons
or replace accessible report evidence with a snippet.

Avoid causal claims from arithmetic alone. Fee-adjusted negative performance does
not identify investment versus timing, slippage and missed-fill effects. A hedge's
assumed sensitivity is not an estimated beta or guaranteed loss ceiling. Inspect
every scenario payoff instead of summarizing from only the largest shock. Preserve
the direction of chronology: information and decisions must be available no later
than the applicable as-of cutoff, subject to the implemented causal timing rules.

Before delivering, compare the explanation with the bound inputs and actual result.
Label analyst proposals and interpretations separately. State which requested work
is incomplete and why. Neither a clean receipt nor two matching model answers proves
universal model independence, source truth or investment performance.

## Review retained model runs against the original request

Establish the authoritative original requested input or mandate from the supplied
request and its declared source pointer (for example, `requested_inputs`),
separately from each run's own request.
Compare each run's complete resolved parameters and source selections against that
authority. Report unauthorized changes as request-fidelity failures even when the
run's own bindings, helper invocation and arithmetic are internally consistent.
If authority is missing or ambiguous, retain that uncertainty rather than choosing
a run's request as the baseline.

Assess request fidelity, helper execution, artifact completeness, numerical replay
and final explanation separately. A shared contract hash covers only that contract,
not necessarily all inputs; inspect the scope of the hash before claiming identity.
Replaying a run's own inputs can verify its calculation but cannot establish that
it answered the original request. Preserve original runs and retain new replays
separately; do not repair historical evidence in place.
