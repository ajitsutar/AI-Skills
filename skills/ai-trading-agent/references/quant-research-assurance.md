# Quantitative research assurance

Use these checks to substantiate a research claim. They are not conditions for
carrying out an authorized trade, certifications of alpha, or substitutes for
unavailable source data. Retain evidence outside the installed skill.

## Choose the actual research contract

Freeze the universe, identity convention, decision and execution clocks, feature
lookbacks, return basis, valuation policy, cash/dividend treatment, benchmark and
cost assumptions before ranking strategies. A current constituent roster supports
a survivor-conditioned study; it does not reproduce historical index membership.
Running a current language model with old inputs does not remove knowledge in
its training. Historical AI reselection remains exploratory unless that limitation
is independently resolved.

[Data contracts](quant-data-contracts.md) provide strategy-specific required-field
grids, historical identity episodes, publication/revision-aware source adapters and
optional revision-aware price refresh. Carry the returned readiness status,
universe mode, exclusions and unresolved requirements into every report headline
and export. Never summarize a modeled zero-gap grid as observed completeness.
Signal, valuation and execution evidence answer different questions. An unquoted
child interest can have an explicitly modeled value without an executable price.

`data.strategy_readiness`, `data.security_snapshot`, `data.source_features` and
`data.price_refresh` are pure workbench operations. Full fetching remains the
default. Tail reuse requires opt-in and verifiable current prefix evidence; an
unchanged recent overlap alone cannot establish unchanged old adjusted prices.
Retain actual elapsed time, transferred bytes, retries and stored bytes separately
from reconciliation results. Do not advertise download savings from a fixture.

## Connect risk, implementation and evidence

[Holdings accounting](holdings-event-ledger.md) joins lots, corporate actions,
receivables, settlement, tax reserves and dated withdrawals in
`backtest.holdings_ledger`. Keep unknown taxes or marks unresolved. Its cash and
unit reconciliation is not a time-weighted performance calculation; choose the
return-accounting operation appropriate to the supplied cash-flow convention.

Use the ledger's `tax_evidence` and `conclusion_facts` when comparing scenarios.
A cash or declared-payment difference is conditional arithmetic; it does not
identify another scenario's missing tax amount. Even a zero remaining declared
balance leaves unresolved taxes unknown. Cite the event's supplied amount or
rate-and-gain derivation for a tax figure, and retain null total liability and
net-of-tax value when inputs are missing. Another scenario's explicit tax is not
evidence of the missing amount in this scenario.

[Risk diagnostics](risk-diagnostics.md) and [GARCH](garch-volatility.md) distinguish
fit convergence, stationarity, residual failures, useful variance forecasting and
tail sample size. Use `risk.empirical_tail`, `risk.conditional_portfolio`,
`portfolio.construct` and `portfolio.sensitivity` with compatible return units and
explicit denominators. Freeze sensitivity cases before inspecting them; preserve
failures and revised hypotheses. A variance forecast supplies no expected return
or probability of achieving a spending target.

### Concentration scope in native allocation comparisons

Use `portfolio.construct` and `portfolio.sensitivity`'s generated
`concentration_summary` with their `concentration_diagnostics`; retain every
prespecified alternative and failed result without selecting a winner. Existing
weights, covariance risk, costs and optimality certificates are separate facts.
The diagnostic's `nav_squared_weight_sum_excluding_cash` is the sum of squared
initial-NAV weights for the supplied risky asset IDs. It is a partial squared sum,
not a normalized HHI, and its reciprocal is not an effective asset count.

`risky_position_gross_distribution` normalizes each absolute weight by the stated
`denominator_value = sum(abs(weight))`. Its HHI is the sum of those normalized
shares squared; `effective_equal_weight_count` is the reciprocal of that HHI.
State the denominator and cash exclusion when quoting either metric. Compare
normalized shares when gross exposure changes between scenarios. The nonzero
supplied-position count is separate: the effective count does not establish actual
holdings, independent bets, issuer/sector diversification or covariance risk.
For signed positions the scope is absolute gross exposure, not net ownership;
zero gross exposure leaves HHI and effective count unavailable.

No cash bucket, collateral or borrow reserve is added to this risky distribution.
`whole_account_concentration` is explicitly `NOT_COMPUTED`. A supplied asset ID
literally named CASH is still an asset ID, not an inferred cash balance. Do not
relabel these values as whole-account concentration or infer that lower variance
means broader diversification. Failed constructions retain unavailable weights
and the sensitivity summary reports concentration unavailable for those cases.
The calculation remains advisory and grants no execution permission.


[Analyst source extraction](analyst-source-adapter.md) supports
`analyst.extract_table` and `analyst.earnings_basis`. Preserve source text and
every accepted/excluded row. An aggregate target table is not a full analyst
report. Keep earnings periods, GAAP/adjusted definitions and split bases distinct;
do not average incompatible publisher statistics. Continue the existing
[sentiment review](news-and-guidance.md#complete-the-sentiment-review), retaining
contradictory evidence and distinguishing qualitative judgment from calibrated
measured sentiment.

## Retain losing experiments and test releases

[Experiment records](experiment-registry.md) retain prompts, data/code/runtime
identities, conventions, revisions, failures, outcomes and prospective captures.
Pure `experiment.validate_attempt` and `experiment.overlap_review` support replay.
Registry mutations are explicit CLI/API actions; never put them in a replay job.
Report overlap between screening and evaluation periods. Selection of finalists
using the last year contaminates a five-year evaluation containing that same year.
Use purged walk-forward splits, prespecified negative controls, bootstrap/HAC and
multiple-testing tools only with their stated assumptions and the full retained
trial inventory. Neither a high Sharpe ratio nor repeated model agreement repairs
selection bias. A future paper record must accumulate in real time.

[Review packets](review-packet.md) retain criterion dependencies, source/assisted arms and original-response evidence. [Institutional deployment evidence](institutional-acceptance.md) composes native platform/data/rights evidence for one declared host, package and scope, with retained control files and a prespecified matched value comparison. It does not establish human productivity or alpha from software success.

[Release acceptance](release-acceptance.md) covers artifact-locked environments,
software inventories, frozen fixtures, actual host responses and source rights.
`release.rights_inventory` and `release.grade_response` are pure operations.
Environment installation and file-writing fixture runners stay outside replay.
Populate a capability card from actual receipts. A test on Windows/CPython 3.12
does not certify another OS, model host, data entitlement or broker integration.
Source access and redistribution permission remain separate from software rights.

Every new pure operation is included in the workbench implementation hash and
can be frozen and replayed through the existing source-bound research workflow.
Hashes bind bytes; they do not authenticate publishers, prove a complete search
history, or notarize the local machine clock.
