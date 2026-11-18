# Monthly portfolio validation

Use this guide when a user asks to reconsider stocks and weights monthly over a
historical period, compare an adaptive portfolio with benchmarks, or derive changes
to an investment process. Preserve the requested dates, initial capital, universe,
contributions, reserve treatment and objectives. Examples and proposed constraints
are hypotheses, not global portfolio mandates or learned optimal settings.

## Identify the experiment before calculating

Keep these experiment types separate in inputs, results and conclusions:

| Experiment | What it can establish | Material limitation |
|---|---|---|
| Today's selected names held unchanged | Historical behavior of those exposures | Retrospective selection and survivor bias |
| Same fixed names reset to equal weights monthly | Behavior of a fixed monthly rebalancing control | Neither stock reselection nor adaptive sizing |
| Same fixed names with causal changing weights monthly | Behavior of the frozen sizing rule for those names | Neither stock reselection nor protection against current-name selection bias |
| Frozen deterministic monthly selector and sizing rule | Reproducibility of a causal price-rule control on its declared panel | A price rule is not an AI decision process; a modern panel retains selection bias |
| Retained original historical AI decisions | Replay of those particular recorded decisions and sources | Requires genuine original records, historical universe and source availability |
| New forward AI paper decisions | Sequential evidence on subsequently observed outcomes | A short paper record is not production certification |

An AI asked today to act as though it were years earlier can retain later events
from model training. Suppressing future input rows, changing the prompt date or
using a current model's historical narrative cannot remove that knowledge. Label
such exercises retrospective and exploratory. Do not fabricate original decisions,
claim historical model versions were run, or rename a deterministic control AI.
Actual monthly reselection must retain an eligible set, selected issuer IDs, exits,
entries, target weights and reasons at each decision; fixed labels with changing
weights alone do not satisfy a request to reselect stocks.

## Historical inputs and coverage

For a whole-market request, preserve the exact declared security universe, stable
issuer/security IDs, active and inactive securities, historical membership dates,
share-class treatment, listing changes, delistings and terminal outcomes. Record
acquired, usable, selected and unavailable counts separately for each decision.
Today's active listings or today's index constituents cannot silently stand in for
historical membership. Do not drop failures, bankruptcies or unscored names and
then call the remainder the whole universe. If coverage is incomplete, identify
the exact missing dimensions and label any narrower control explicitly.

Retain source bytes or durable source pointers, currency, units, observation/event
dates, original publication/availability timestamps, revision IDs, retrieval times
and corporate-action conventions. A fiscal period end is not a publication date.
Later restatements and current analyst forecasts are not historical vintages. Price
history alone cannot establish contemporaneous fundamentals, sentiment or analyst
coverage. Missing values are unknown, not zero. A current data download's historical
rows are not automatically a verified point-in-time database.

For supplied revision records, use the implemented `data.asof_snapshot` operation
and the schema in `scripts/point_in_time_data.py` / `examples/point-in-time-data.json`.
It selects records available by a supplied cutoff, preserves revision exclusions
and hashes, and does not acquire data or verify the caller's availability/license
claims. `data.pit_snapshot` is not an implemented alias. Keep membership and source
authenticity evidence alongside the snapshot; a hash identifies bytes, not truth.
See [portable quant methods](portable-quant.md).

## Freeze the design, then use native accounting

Use the [source-bound workflow](source-bound-workflow.md) to retain original inputs,
declare every requested subtask, bind source fields or labeled assumptions, run
available operations, verify the saved directory and obtain its summary. Use
`backtest.portfolio` for period-return accounting with externally retained decisions.
Inspect `quant_workbench.py operations` and `scripts/portfolio_backtest.py` for its
actual argument contract; do not substitute an invented optimizer or scorer.

### Reusable monthly-target and staged-comparison helpers

The following implemented operations are available through `quant_workbench.py`
and the source-bound workflow. They are ordinary offline calculations; none adds
an execution permission or strategy-promotion requirement.

| Operation | Input | Result |
|---|---|---|
| `portfolio.capped_inverse_volatility` | `document` containing positive `volatilities` by symbol, optional `equity_weight` and `cap` | Deterministic long-only capped inverse-volatility weights and pre-fee cash target |
| `backtest.monthly_targets` | `document` with fixed symbols, prices and an extended session calendar | Causal monthly targets, pending targets and explicit failed formations; no NAV calculation |
| `experiment.freeze` | Complete proposed design in `document` | Hash-bound normalized contract before performance work |
| `experiment.rank_stage` | Frozen contract, stage attempts and previous shortlist where applicable | Ranked after-cost metrics, failures and a hash-bound shortlist/selection receipt |

Use `scripts/monthly_experiment.py` for the complete argument validation and
`examples/fictional-monthly-experiment.json` for a runnable workbench example.
The direct CLI supports `weights`, `targets`, `freeze` and `rank` with an input
JSON file and `--output` outside the skill. Output creation is exclusive; preserve
an earlier attempt rather than overwriting it. There is no download in these
helpers. Supplied result hashes and calendar/source declarations require the
usual source-bound evidence; they are not independent authentication.

**Monthly target contract.** `composition_mode` must be `fixed_adaptive`,
`fixed_equal` or `reselection`. The target generator implements the first two and
rejects `reselection`: it does not invent eligible histories or a stock selector.
An actual reselection study can still retain externally justified changing
decisions and account for them with `backtest.portfolio` as described below.

Supply `symbols`, timezone-aware `as_of`, inclusive formation dates `start` and
`end`, `calendar_evidence`, and `calendar` rows with `session_date` and `close_utc`.
The calendar must extend into the month after `end`; the last observed price is
never used as proof of month-end. Include actual exchange holidays, early closes
and timezone rules. The helper checks order and timing, not whether a declared
calendar is an authentic complete exchange calendar.

Each `observations` row has `session_date`, timezone-aware `available_at`, and
`prices` containing exactly the fixed symbols. Prices must be finite and positive;
availability cannot precede the session close or exceed `as_of`. All lookback
sessions must exist, and every price used must have been available by the decision.
No missing price is filled and no failed formation is silently dropped. Read the
returned `failures`; an `INCOMPLETE_TARGETS` result is not a completed backtest.
All prices must use the retained compatible total-return/adjustment convention
and source vintage. Never combine an obsolete adjusted-price prefix with a newly
revised tail merely because local hashes verify.

Optional `lookback` defaults to 60 daily returns (61 price marks), `ddof` to 1,
`equity_weight` to 0.99, `cap` to 0.15 and `decision_delay_seconds` to 1. These are
explicit helper defaults, not a recommended portfolio policy. Outputs retain the
resolved choices. Adaptive weights use sample volatility and waterfill rather
than clipping followed by renormalization. Globally infeasible caps reject the
request; zero-volatility assets cause a recorded failed formation. Equal-weight mode retains zero-volatility
names because it does not divide by their volatility. Both modes keep the complete
fixed stock list. Identical inputs produce stable weights independent of dict order.

Decisions are known after the actual month-end close and target the next supplied
session's close. Use that execution close as the next native accounting period's
`start`; its `end` price earns the first return on new targets. Earlier holdings
earn through execution. A last-month target whose execution lies after `as_of` is
explicitly `PENDING` and must not earn returns in the completed test. Caps and cash
are **pre-fee targets**, not continuously maintained caps or post-fee floors.
The target generator does not solve cost-funded quantities: retain a sufficient
buffer or separately size costs, then let the native accounting cash-floor check
reject an underfunded purchase. Start in cash to charge the initial purchase.

**Staged comparison contract.** `experiment.freeze` accepts full ordered
`candidates` (unique `candidate_id`, fixed `symbols`), `composition_mode`,
`screen_window` and `final_window` (`start`/`end` dates), `weighting_rule`,
`benchmark`, `execution_convention`, `cash_treatment`, `tax_treatment`,
`universe_vintage`, `source_contract`, `base_one_way_cost_bps`,
`stress_one_way_cost_bps`, and timezone-aware `sealed_at`. Optional `counts`
defaults to `{screen: 10, finalists: 5, selected: 2}`; explicit user counts
override it. Freeze the design before reading new candidate performance. Keep
composition, weighting and accounting conventions unchanged between stages.

The fixed scoring rule is 50% CAGR percentile, 25% Sharpe percentile and 25%
negative-drawdown percentile. Tied observations receive average ordinal ranks;
score ties use lower annual gross turnover, then candidate ID. Metrics are not
rounded before ranking. Stress-cost results are separate sensitivities, not a
second opportunity to tune the shortlist.
Explicit incompatible `score` or `tie_break` fields are rejected rather than
silently replaced. Use a separately declared, tested ranking adapter if the user
chooses another ranking policy; this helper does not implement arbitrary scorers.

For `experiment.rank_stage`, supply `frozen`, `stage` (`screen` or `final`),
`sealed_at`, and one `results` row for **every** expected candidate. Each row
contains `candidate_id`, exact stage `window`, `one_way_cost_bps`, and `status`.
A `COMPUTED` row includes the retained native result's `result_sha256`, its
`accounting_input_sha256`, and `result_contract`. That descriptor must contain the
matching `experiment_contract_sha256`, exact candidate `symbols` in frozen order,
and the frozen `weighting_rule`, `execution_convention`, `cash_treatment`,
`tax_treatment`, `benchmark` and `source_contract`. Derive this descriptor from the
actual run inputs rather than blindly copying the proposed design. Bind the whole
actual inputs and results in the source-bound workflow. The helper rejects a
changed composition or rule, but cannot authenticate a falsely declared descriptor.
Also supply
`metrics`: `cagr`, consistently annualized `sharpe`, positive loss fraction
`max_drawdown`, and `annual_gross_turnover`. A `FAILED` or `UNPRICEABLE` row must
include its `reason`. No failed attempt may be replaced silently; insufficient
valid candidates produces `INSUFFICIENT_VALID_CANDIDATES` and no selection.

The final stage additionally requires the exact `screen_receipt` and
`final_data_opened_at` later than its seal and no later than the final seal.
The helper replays the prior ranking and rejects a changed contract or shortlist.
It cannot independently prove supplied timestamps, absence of prior peeking or
that the source supports the metrics. Retain the actual sequential workflow files
and source bindings. The one-year window commonly overlaps the five-year window;
overlap is reported explicitly and **never establishes an untouched holdout**.
Current-name selection and current-vintage histories retain their hindsight and
survivorship limitations even when every calculation and hash verifies.

Before running performance, freeze the universe, selection rule or AI prompt and
model identity, feature lookbacks, publication cutoff, execution lag, benchmark,
cash return, costs, rebalance calendar, missing-data rules, corporate actions and
metrics. Retain every attempted variant. A long-only cap, turnover limit, momentum
lookback or sector limit is a candidate hypothesis until separately justified; do
not tune it on the same window and call it a learned optimal constraint. No fixed
capital amount, date range, issuer count or reserve is imposed by this guide.

The native engine accepts a fixed superset of symbols and supplied zero/nonzero
weights, so an adapter can represent changing selections if the full historical
superset and membership evidence exist. This capability does not supply missing
historical memberships or choose stocks. Its evidence fields and tradability flags
are caller declarations; `point_in_time_evidence_verified` remains false.

For retained position evidence, set the optional document field
`include_positions: true`. It defaults to false, preserving the legacy curve.
The trace records opening and post-trade symbol market values and cash, signed
trade notionals, ending holdings and ending weights at supplied period boundaries,
plus final weights. These are dollar/value positions, not share counts or verified
fills. Ending weights are unknown (`null`) when ending NAV is zero. The trace
does not provide issuer look-through, historical membership proof or intraperiod
risk, and does not change the return or cost calculation.

### Calendar and executable timing

Use an explicit historical exchange calendar, session close and timezone, including
early closes and holidays. Month-end means the declared last trading session, not
an assumed calendar date. Record signal observation, when all source data became
available, decision completion, intended execution and actual return price bases.

For close-only data, a signal calculated from the month-end close can execute at
the next trading-session close; new weights first earn the subsequent close-to-close
interval. Existing holdings earn returns through that execution close. If next-open
execution is desired, supply executable open prices and account for overnight
holdings separately. Do not infer such fills from adjusted closing prices.

The native `known_at < period.start` test is necessary but does not authenticate the
supplied return's price basis. Relabeling a close-to-close return as next-day does
not make the previous close executable. Disclose this adapter responsibility.
Give every comparator the same initial timing opportunity and final valuation mark.
An initial signal may precede the first requested mark only if its data and decision
actually satisfy that cutoff; otherwise start in cash and use the declared lag.

### Costs, reserves, distributions and comparators

`initial_weights` assigns starting holdings without entry costs. For an after-cost
study, start from cash and retain an explicit first purchase decision, or explicitly
exclude entry costs consistently for all comparators. Positive costs plus targets
summing to 100% exceed available cash; reserve fees or solve fee-inclusive sizing.
Do not turn off costs merely to avoid `CASH_FLOOR_AFTER_COSTS`.

Declare whether reserve cash is inside initial NAV or external to the tested equity
sleeve, how entry/rebalance fees are funded, and whether reserve interest and later
transfers enter the study. Never add outside cash to one strategy's terminal value
while benchmarking only its stock budget. Distinguish the native post-trade cash
fraction check from a continuously maintained dollar reserve.

The native engine compounds supplied `benchmark_return` values without separately
charging benchmark trades. Prefer separate same-engine comparator runs with matched
entry, terminal and cash conventions, or label any gross-index/net-strategy difference
explicitly. Buy-and-hold has no repeated target decisions; monthly equal weighting
does. Gross traded notional is absolute buys plus absolute sells, so state the
turnover denominator and one-way cost units. Keep base and sensitivity assumptions
distinct from measured fills. Do not invent liquidation at the terminal mark.

Use compatible dividend-reinvested total returns for the primary equity comparisons.
An S&P 500 price index and its total-return index are different benchmarks. An
investable U.S. index ETF and a broad global ETF may be appropriate disclosed
comparators; verify their actual mandates and return conventions. Total-return
adjustments already include distributions: do not credit dividends again. ETF return
history already includes fund expense drag: do not deduct today's expense ratio
again or assume it applied unchanged in every prior year. Retain split/spin-off and
delisting treatment. Use a historical available cash series or disclose zero yield;
do not apply today's cash rate retroactively. State investor-tax exclusions.

## Evaluation and forward evidence

Predeclare after-cost total return, actual-elapsed-time CAGR, maximum drawdown and
active returns versus each benchmark. Report risk and implementation diagnostics
such as frequency-labeled volatility, worst month, time underwater, rolling returns,
concentration, cash exposure, turnover, costs and changes in selected names/weights.
Compute drawdown from daily NAV when available; monthly marks miss intramonth troughs.
The native `validation.tail` / `tail_risk` reports input-period empirical tail loss,
drawdown and total return, not CAGR or Sharpe. Preserve its sparse-tail warning.
Use supported numerical operations and retained result pointers; missing metrics
need an explicitly identified calculation rather than an unrun claim.

A development slice followed by a later chronological evaluation slice is useful,
but is not an untouched holdout if rules were tuned after seeing it or a current
model knows its outcomes. Preserve contamination and multiple-trial limitations.
Do not infer profit/crash probabilities from a short sample or call agreement across
models proof of historical independence. Software tests, exploratory performance
and validated investment effectiveness are separate conclusions.

For genuinely new AI observations, retain each prompt, available source bundle,
model/version, tools, raw response, rejected attempts, constraints and decision hash
before the first executable trade. Archive outcomes later without rewriting prior
decisions. Model upgrades create distinct retained versions. Paper accounting and
these research requirements impose no broker execution gate or new approval flow.
