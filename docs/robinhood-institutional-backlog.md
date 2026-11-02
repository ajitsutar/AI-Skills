# Institutional research readiness backlog

Updated November 2, 2026. Publication baseline: `robinhood-ai-trading-agent` **5.4.1**.

The first target is a supervised U.S.-equity research and portfolio-risk assistant.
A portfolio manager owns investment decisions, sizing and portfolio outcomes;
a quant develops and challenges the data, models and calculations supporting
those decisions. One person may perform both roles. This backlog covers both
perspectives without claiming that tested software establishes investment skill.

This is a prioritized development plan, not authorization to start a pilot,
purchase data, inspect private model sessions or submit trades. Its priorities
do not change any existing comparison-case schedule. Research checks are advisory
and add no skill execution gates.

## Completed foundation

The reviewed 5.4.0 release passed **1,685 tests with no skips**, plus **12 release
preservation tests**. A fresh Windows/CPython 3.12 environment installed from
45 artifact-hashed dependency wheels. Fourteen new pure operations support
source-bound readiness/identity, holdings and tax/settlement accounting, analyst
extraction, portfolio risk, experiment review and release evidence. Independent
reviews and regression tests addressed material accounting, optimization,
source-binding and report-export defects.

The 5.4.1 publication patch moves existing instructions into a linked reference
to meet the repository's entry-file limit and adds whitespace around one test's
matrix-multiplication operator. It preserves calculation behavior. The completed
foundation results above describe the reviewed 5.4.0 run; publication checks are
recorded separately rather than retroactively relabeling that evidence.

5.4.0 tested-foundation manifest SHA-256:
`067fb10ceab4319350381d34994ef4a55464eda76bf61e662ace0235dc8f03c6`.

See [research assurance](../skills/robinhood-ai-trading-agent/references/quant-research-assurance.md)
and [release acceptance](../skills/robinhood-ai-trading-agent/references/release-acceptance.md).
These are scoped local software results. Complete historical membership and
delisting data, provider entitlements, independent host acceptance and predictive
performance remain separate evidence requirements. Raw data, private comparison
responses and local review ledgers are not distributed with this repository.

## Priority and status

- **P0:** Establish a credible supervised pilot with a declared scope.
- **P1:** Demonstrate dependable recurring use and challenge the selected methods.
- **P2:** Extend to the specific institution's operational deployment.

All items below are **planned, not started** unless an external dependency is
explicitly marked. Existing software is reused; a planned integration or pilot
does not mean the underlying helper is missing. Start in order within each tier,
subject to dependencies. HF-09 review should run alongside HF-05 evaluation;
the ranking does not justify postponing independent challenge until after results.

| Rank / ID | Priority | Deliverable | Acceptance criteria | Dependencies / owner role |
|---|---|---|---|---|
| 1 / HF-01 | P0 | Define the manager pilot | Freeze one workflow, intended decisions, universe, horizon, constraints, reviewer, baselines and evaluation measures. Separate research usefulness from return claims. Record exclusions and the criteria for expanding scope. | Manager input; portfolio manager + research lead |
| 2 / HF-02 | P0 | Qualify actual data and rights | Inventory exact sources, publication/retrieval clocks and permitted retrieval, retention, display and redistribution. Verify identity, actions, fundamentals and estimates for every pilot-required field. Expose historical membership/delisting gaps; never promote modeled values to observations. Preserve dated terms evidence and unresolved rights. | HF-01; provider access/rights may be external; data lead + rights reviewer |
| 3 / HF-03 | P0 | Produce decision-ready investment briefs | Every brief includes thesis, differentiated reasoning, valuation assumptions, catalysts, downside, contrary evidence, invalidation conditions and source dates. Distinguish full analyst reports from excerpts/aggregate targets. Reviewer can trace material claims to evidence and identify unknowns. | HF-01, HF-02; research analyst + manager |
| 4 / HF-04 | P0 | Evaluate proposals in the actual portfolio | Reconcile dated positions, cash and entitlements. Show incremental concentration, sector/factor exposure, stress losses, liquidity and portfolio constraints. Reconcile denominator and currency; state uncovered positions and unsupported risk dimensions. | HF-01, HF-02, supplied portfolio; portfolio/risk lead |
| 5 / HF-05 | P1 | Run a prospective usefulness study | Preserve first briefs/weights, revisions and outcomes. Measure research time, factual errors, overlooked risks and reviewer usefulness against the declared baseline. Assess forward returns separately with comparable benchmarks and realistic costs. No fixed calendar duration automatically establishes alpha. | HF-03, HF-04; HF-09 reviewed design; elapsed observations; pilot owner |
| 6 / HF-06 | P1 | Validate costs, liquidity and capacity | Compare fees, slippage, turnover and impact assumptions with observed evidence for the chosen strategy and size. Long/short scope additionally requires borrow availability/cost, financing, recall, margin and squeeze scenarios. Report unavailable inputs instead of zero costs. | HF-01, HF-02; relevant market/broker evidence; execution + risk lead |
| 7 / HF-07 | P1 | Make recurring operation dependable | Demonstrate freshness alerts, bounded retries, overlap prevention, checkpoint recovery, duplicate suppression and reconciliation after partial failure. Measure actual acquisition time, transferred bytes, retries and retained storage. Verify full-versus-incremental equality on revisions and exercise full-refresh fallback. | HF-02, HF-04; data/platform engineer |
| 8 / HF-08 | P1 | Complete claimed host/platform acceptance | Execute identical frozen cases in each claimed environment; retain first responses, errors, date/scope mismatches and disagreements. Separately test installed-package access and deterministic replay. Update capability claims only from actual evidence. | **Access-dependent:** Muse/Claude fixtures remain unsubmitted after private-session inspection was blocked; separate inspection authorization is still required. Other OS environments need actual tests. Validation lead |
| 9 / HF-09 | P1 | Independently challenge the chosen methodology | Review conceptual assumptions, leakage, survivor/selection bias, untouched evaluation, negative controls, simple benchmarks and sensitivity. Preserve all trials and revisions; assess multiple testing under justified assumptions. Separate arithmetic correctness, risk forecasting and predictive returns. | HF-01, HF-02; independent reviewer; begin before HF-05 results are examined |
| 10 / HF-10 | P2 | Implement the target deployment's operations and integrations | Define the deployment first, then test access controls, secrets isolation, private-data retention, incident recovery and version rollback. Any execution integration needs idempotent instructions, partial/rejected-fill handling, broker reconciliation and observed results. Validate support and recovery expectations appropriate to the deployment. | Pilot findings, target architecture and relevant permissions; platform/security/operations leads |

## First milestone: supervised research pilot

Close HF-01 through HF-04 with a named reviewer and evidence for the actual scope.
The manager must be able to answer: why this idea, why this size, what could break
the thesis, how it changes existing risk, and how the position could be exited.
Where cost or liquidity evidence is needed, pull the relevant HF-06 work forward.
Do not present an unqualified recommendation when a material input is unresolved.

Freeze HF-05's measures and HF-09's evaluation design before collecting results.
Research utility can be valuable without a demonstrated stock-selection edge.
Claims about investment performance require their own prospective evidence after
costs and relevant market/factor exposures; a successful fixture or agreement
between models does not supply that evidence.

## Maintaining this backlog

For each item, retain status, accountable owner, dependency resolution, dated
acceptance evidence and known limits. Split a large item into linked subtasks
before implementation. Keep failed attempts and changed assumptions visible.
Mark completion only against the acceptance criteria, and label external blockers
explicitly. Keep confidential evidence outside the public repository and publish
only appropriately reviewed summaries and portable regressions.
