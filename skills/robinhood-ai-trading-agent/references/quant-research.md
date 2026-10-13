# Quant research methods and adoption decisions

Research references reviewed October 12, 2026. Sources below support method choices; none
endorses this package or proves its performance. The development record identifies
local implementations of these methods; the bounded source comparison and its
limits are in [PROVENANCE.md](../PROVENANCE.md). Method citations do not assert
ownership of the mathematics or redistribute publication text or source code.

## Statistical evidence

Split chronologically, train preprocessing on training data only, purge overlapping
forward labels, and leave a declared time gap. `validation.folds` uses prior-only
expanding training sets; it does not implement combinatorial symmetric CV or PBO.
Keep a final untouched test and paper period even when walk-forward results look good.
Track all hyperparameter choices, feature sets, universes and discarded experiments.

`validation.hac` uses a Bartlett Newey–West long-run variance for a mean and an
asymptotic normal interval. Its lag count must be chosen before looking at significance.
Small samples and strong persistence can still produce poor inference. Pair it with
`validation.bootstrap`, a seeded circular moving-block percentile interval, and
report sensitivity to economically plausible block lengths. Bootstrap assumes
approximate stationarity; it cannot manufacture crisis observations or prove alpha.

`validation.holm` implements Holm's step-down Bonferroni procedure and controls
familywise testing over the complete supplied family.
It does not repair unrecorded trials. `validation.sharpe` reports unannualized PSR
and DSR diagnostics using skewness, Pearson kurtosis and cross-trial Sharpe variance.
The selected series must be net excess returns at the same frequency as trial
Sharpes. The effective independent-trial count needs a retained justification;
do not choose a low number to pass. The simple PSR probability is not interpretable
under serial dependence without additional justification. It is never a posterior
probability that the strategy will make money.

`validation.promotion` recomputes HAC, Holm and a block-bootstrap lower bound from
the selected strategy and its complete aligned trial family. Its thresholds are
illustrative analytical choices, not universal performance standards or execution prerequisites.
Source completeness, actual untouched selection and forward-paper evidence remain
independent requirements in `strategy_validation.py`.

Sources: [Bailey and López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf),
[Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf),
[Newey and West, HAC covariance](https://www.nber.org/papers/t0055),
[Robust Inference in Time Series Regression](https://www.nber.org/papers/w32554),
[Holm, A Simple Sequentially Rejective Multiple Test Procedure (1979)](https://www.jstor.org/stable/4615733),
and [Politis and Romano, A Circular Block-Resampling Procedure for Stationary Data
(Stanford technical report, 1991)](https://statistics.stanford.edu/technical-reports/circular-block-resampling-procedure-stationary-data).
The bootstrap helper samples fixed-length blocks with wraparound and trims the
concatenated sample to the original length. It does not implement the distinct
stationary bootstrap with geometrically distributed block lengths. These are
method references; the package does not redistribute their paper text or code.

## Risk and construction

Existing covariance analytics use a declared shrinkage toward the diagonal; they
are not the automatically estimated Ledoit–Wolf algorithm. Audit aligned returns,
sampling frequency, volatility changes and estimation windows. The new allocator
requires a symmetric positive-semidefinite covariance at the actual allocation
horizon, rather than silently repairing a bad matrix or rescaling it to decades.

`portfolio.construct` minimizes variance and implementation/borrow costs, or uses
an explicitly calibrated robust return objective. It penalizes uncertainty with
the supplied absolute-position uncertainty budget. Hard constraints are audited
again on the actual weights after optimization. Infeasibility is returned without
relaxing cash, liquidity, concentration or scenario bounds. Compare a simple
allocation baseline; tiny historical differences do not establish optimality.
The solver is single-period and continuous; it is not multi-period stochastic
control, integer tax-lot optimization or a margin model.

`validation.tail` computes empirical loss VaR and the integral of the worst tail,
including a fractional boundary observation. It reports effective tail sample size.
Negative loss values mean gains. Do not floor them to zero without disclosure.
Historical ES is not a worst-case bound; add rate, credit, correlation, FX,
liquidity, counterparty, default and gap stresses appropriate to the book.

`risk.option` in `scripts/multi_asset_risk.py` uses Black-Scholes-Merton
European option pricing with a continuous dividend yield, constant volatility and
constant continuously compounded rates. Its delta, gamma and vega are derivatives
of that model; vega is reported per one percentage-point volatility change. The
expiry/zero-volatility branch reports discounted intrinsic value and withholds
kink Greeks. These assumptions do not model early exercise, discrete dividends,
volatility smiles or an executable market price. The helper is a local
implementation of the published equations using SciPy's normal CDF/PDF, not an
imported options-pricing implementation.

Foundational sources: [Black and Scholes, The Pricing of Options and Corporate
Liabilities (1973)](https://www.journals.uchicago.edu/doi/10.1086/260062),
[Merton, Theory of Rational Option Pricing (1973)](https://www.jstor.org/stable/3003143),
and [Merton's preceding MIT working paper (1971)](https://dspace.mit.edu/entities/publication/6e05a2fa-478f-41e6-9e69-a06532002236).
These citations credit the model, not any claim that the package invented it or
has permission to redistribute the publications.

Sources: [Ledoit and Wolf, covariance shrinkage](https://ledoit.net/honey.pdf),
[Boyd et al., Multi-Period Trading via Convex Optimization](https://stanford.edu/~boyd/papers/cvx_portfolio.html),
[Cvxportfolio constraint documentation](https://www.cvxportfolio.com/en/1.5.0/constraints.html),
[Basel market-risk framework](https://www.bis.org/committees/bcbs/basel-framework/standard/mar?allChapters=true).
Basel is a risk-method reference here, not a claim that its bank-capital rules
apply to this personal account or that this helper is a regulatory capital engine.

## Costs, capacity and performance

Measure quoted spreads, commissions, impact, delay, unfilled opportunity cost,
borrow, financing, exchange/clearing fees, taxes and FX separately. Coefficients
must come from the intended instrument, order size and venue; do not transplant
institutional execution averages into a small retail account. Stress fees/spreads,
participation and halts. An OHLC touch is not a guaranteed limit fill.

`ops.shortfall` decomposes arrival execution, decision-to-arrival delay, fees and
unfilled opportunity cost with correct buy/sell signs. `backtest.portfolio` is a
period-return accounting simulation with causal precomputed weights, cash returns,
explicit costs and capacity. It cannot validate intraday fills or cash recycling.
Use existing `strategy_lab.py` for its supported completed-bar strategies, and
paper-test real order behavior before any promotion.

Report TWR for strategy performance, XIRR for investor cash-flow experience, and
benchmark-relative/factor attribution separately. XIRR returns ambiguity for
nonconventional sign-changing flows rather than choosing a favorable root.
Single-period Brinson–Fachler allocation, selection and interaction must reconcile
to active return and include cash. Do not sum period attribution into a compounded
annual result without a declared linking method.

Sources: [Frazzini, Israel and Moskowitz, Trading Costs](https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs),
[AQR, Transactions Costs: Practical Application](https://www.aqr.com/Insights/Research/White-Papers/Transactions-Costs-Practical-Application),
[CFA Institute, Performance Attribution](https://rpc.cfainstitute.org/research/foundation/2019/performance-attribution),
[CFA Institute, Portfolio Performance Evaluation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/portfolio-performance-evaluation).

## Sources, vintages and governance

SEC API facts are extraction aids, not a substitute for filing/entity/basis review.
Preserve accession, unit, period and filing availability; retain amendments and
conflicts. Do not use a later restatement in an earlier decision. For macro data,
use historical vintages; today's revised FRED series are not necessarily what a
trader knew then. Factor libraries can also change construction conventions and
revise history. Pin their release, units and benchmark rather than comparing
different vintages as if they were model disagreement.

Model inventories need purpose, owner, version, data provenance, allowed use,
validation evidence, limitations, monitoring thresholds and change/retirement rules.
The April 2026 SR 26-2 guidance supersedes SR 11-7; its proportional model-risk
principles inform this workflow, without claiming bank regulatory compliance.
Publication alone is not implementation validation. Online quant/social posts are
hypothesis sources; independently reproduce material claims from primary evidence.

Sources: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[Nareit FFO](https://www.reit.com/glossary/funds-operation-ffo),
[FFIEC public data guidance](https://cdr.ffiec.gov/public/HelpFiles/FAQ.htm),
[FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html),
[Kenneth French data library](https://mba.tuck.dartmouth.edu/pages/Faculty/ken.french/data_library.html),
[Federal Reserve SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm).

These methods address different failure modes. Do not add them as a checklist of
favorable signals or let agreement among correlated models count as independent
evidence. VQM, GARCH and analyst commentary do not together establish expected alpha.
