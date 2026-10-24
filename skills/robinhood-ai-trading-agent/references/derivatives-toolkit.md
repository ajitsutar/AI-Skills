# Offline derivatives research contract

`scripts/derivatives_toolkit.py` supplies original standard-library implementations for five bounded research operations. These computations do not establish broker support, executable quotes, regulatory eligibility, margin sufficiency, delivery readiness or production qualification. No network calls, model downloads, new dependencies, account access or orders occur.

Run an executable example from the skill root:

```text
python scripts/derivatives_toolkit.py --input examples/derivatives-american-option.json --output /new/private/path/result.json
```

The output file is created exclusively; an existing file is never replaced. Python API: `run(document)`. `OPERATIONS` maps five names to their single-input-dictionary mathematical functions; integrators must use `run` to enforce the envelope, currency consistency and final finite-output checks.

## Common schema and reproducibility

Every input requires exactly `schema_version: 1`, `action: "research"`, `operation`, `currency`, `information_cutoff`, `inputs_available_at`, and `inputs`. Currency is an uppercase three-letter identifier supplied by the caller; the library does not certify membership in the ISO currency list. All monetary amounts use this single currency. Operation-specific schemas below are exact: every named field is required; extra fields are rejected, including nested objects. There are no implicit numerical defaults. Missing values, null, Boolean numeric inputs, NaN and infinity are rejected. Rates, yields and volatility are annual decimal fractions (`0.05` means 5%, not 0.05%). Prices and amounts are unrounded binary64 values unless the futures rounding contract explicitly applies. Output contains `resolved_inputs` and a versioned `formula_id`.

Both envelope timestamps must be exact timezone-aware ISO instants with seconds and a valid `Z` or `HH:MM` offset (up to six fractional-second digits). `inputs_available_at <= information_cutoff` is required and asserts the entire input packet, including supplied assumptions, was available by that instant. This assertion is retained, not independently authenticated. The workbench also requires `information_cutoff <= contract.as_of`. Inputs must come from the same declared valuation cutoff and a permitted data source. The standalone engine does not fetch quotes, prove data availability, calculate a trading calendar, or turn a model value into a trade recommendation. Preserve input and output together. Repeatability under identical inputs is not evidence of predictive accuracy.

## Vanilla option: `option_crr`

Exact inputs:

| Field | Domain and meaning |
|---|---|
| `spot`, `strike` | Positive currency amount per one underlying unit; do not multiply by an option contract multiplier here. |
| `time_years` | Supplied time to expiry, from 0 through 100 years. No date/day-count inference. |
| `risk_free_rate` | Continuously compounded annual decimal rate, between -5 and 5. Negative rates supported. |
| `dividend_yield` | Constant continuously compounded annual yield, from 0 through 5. |
| `volatility` | Annualized log-return volatility, from 0 through 5. |
| `steps` | Integer from 1 through 1000. |
| `right`, `exercise` | `call`/`put`; `american`/`european`. |
| `dividend_model` | Exactly `continuous_yield`. |
| `rate_compounding` | Exactly `continuous`. |

For each step `dt=T/N`, the Cox–Ross–Rubinstein tree uses `u=exp(sigma*sqrt(dt))`, `d=1/u`, and `p=(exp((r-q)*dt)-d)/(u-d)`. Backward continuation is `exp(-r*dt)*((1-p)*V_down+p*V_up)`. An American node takes the larger of continuation and immediate intrinsic value. A European node permits exercise only at expiry. Output `value_per_underlying_unit` must be multiplied by a separately verified contract multiplier to calculate a contract value. At `T=0`, intrinsic is exact. At zero volatility, discounted intrinsic is evaluated along the deterministic risk-neutral path, at all supplied grid dates for American exercise, or expiry for European exercise.

American exercise is approximated at grid dates; continuous-time convergence is **not verified** by a single run. Repeat with increasingly fine grids and retain discrepancies. Inadmissible `p` is rejected (`CRR_ARBITRAGE_GRID`), never clipped or silently fixed by increasing steps. Extreme numerical trees are rejected. No discrete cash dividend schedule, stock split, early assignment simulation, borrow fee, stochastic rate/volatility, exotic payoff, option-on-future or settlement mechanics is modeled. Do not silently convert discrete dividends into continuous yield.

The one-step golden fixture `S=K=100`, `T=1`, `r=q=0`, `sigma=ln(2)` has `u=2`, `d=0.5`, `p=1/3`: either vanilla right has value `100/3`. Tests also verify European put-call parity under negative rates and yield, an American put premium, expiry, zero volatility, and convergence toward the independent ATM Black–Scholes identity `100*erf(0.1/sqrt(2))`.

## Implied volatility: `implied_volatility`

Exact inputs: `option` (the exact option schema above **without** `volatility`), `market_price` (nonnegative per-underlying-unit premium), `volatility_lower`, `volatility_upper` (strictly positive decimal bounds, lower < upper <= 5), `price_tolerance` (strictly positive premium-unit tolerance), and `max_iterations` (integer 1–100). Use the correct exercise/dividend model and the same units as the observed premium. Both bracket endpoints must be admissible CRR grids. No endpoint is silently adjusted. There is no hidden volatility cap beyond the declared computational maximum.

The solver checks conservative model-consistent economic bounds, reprices both supplied volatility endpoints, then bisects using the same finite tree. European bounds use discounted spot and strike. American lower bounds use intrinsic; upper bounds use spot for calls and `K*exp(max(-r*T,0))` for puts, allowing negative rates. Intermediate values inconsistent with the current price bracket stop as `NON_MONOTONE_BRACKET`. A converged result requires absolute price residual at most `price_tolerance`; it does not prove uniqueness, market liquidity, continuous-time convergence or volatility precision. Flat or boundary prices deliberately return no volatility estimate.

Possible statuses are `CONVERGED`, `NOT_IDENTIFIABLE_AT_EXPIRY`, `PRICE_INCONSISTENT_AT_EXPIRY`, `PRICE_OUTSIDE_ECONOMIC_BOUNDS`, `PRICE_OUTSIDE_VOLATILITY_BRACKET`, `BOUNDARY_OR_FLAT_PRICE_NOT_IDENTIFIED`, `NON_MONOTONE_BRACKET`, and `MAX_ITERATIONS`. Only `CONVERGED` provides `implied_volatility`; retain status and residual in reports. This is implied volatility under a particular supplied model and grid, not realized-volatility forecasting.

`derivatives-implied-volatility.json` uses the independent one-step `100/3` premium above and should recover approximately `ln(2)=0.6931471805599453`.

## FX forward: `fx_forward`

Exact inputs: `spot_domestic_per_foreign` (positive), `domestic_currency`, `foreign_currency` (distinct uppercase three-letter identifiers), `domestic_rate`, `foreign_rate`, `time_years` (nonnegative), and `compounding` (`simple` or `continuous`). Envelope currency must equal domestic currency. Spot and forward are units of domestic currency per **one** foreign unit. Both rates must be supplied on the same declared compounding/time basis.

Simple covered interest parity is `F=S*(1+rd*T)/(1+rf*T)`; both accumulation factors must be positive. Continuous compounding is `F=S*exp((rd-rf)*T)`. `forward_points=F-S` is in quote units, not pip-scaled. No basis, counterparty credit, funding spread, transaction cost, spot-date calendar or collateral adjustment is included. This idealized no-arbitrage forward is **not a forecast** of the future spot rate. Example USD per EUR: `S=1.2`, rates 5% and 2%, one year simple gives `F=1.2352941176470589`. Reversing currency and rate orientation produces the reciprocal.

## Fixed bond cashflows: `bond_cashflows`

Exact inputs: `par` (positive aggregate nominal amount), `settlement_date` (`YYYY-MM-DD`), `cashflows` (1–1000 objects with exactly `date` and positive `amount`), `cashflows_complete: true`, `noncallable_fixed: true`, `yield_rate` (annual nominal decimal yield), `compounding_per_year` (integer 1–365), `discount_day_count: "ACT365F"`, and `accrual` as below. Cashflows are in strictly increasing dates **after** settlement; combine coupon and principal paid on the same date into one amount. Cashflow completeness, currency consistency and noncallability are caller assertions, not independently verified.

Discount times are actual calendar days from settlement divided by 365. Dirty value is `sum(CF_i*(1+y/m)^(-m*t_i))`; `1+y/m` must be positive, and negative yields are allowed. Clean value is dirty value minus accrued interest. Both aggregate amounts and quote prices per 100 par are returned. This explicit ACT365F model is not a claim to implement every bond market's quoted-yield convention.

Choose exactly one accrual schema:

- `{"method":"supplied_amount","amount":...}`: nonnegative independently obtained accrued interest, including zero. This is the path for unsupported market day counts or ex-coupon conventions only after the caller independently establishes the correct nonnegative amount.
- `{"method":"ACT365F" or "ACT360","annual_coupon_rate":...,"last_coupon_date":"YYYY-MM-DD","next_coupon_date":"YYYY-MM-DD"}`: nonnegative fixed annual coupon rate; accrual is `par*rate*actual_days/365` or `/360`. Require last coupon <= settlement < next coupon, and next coupon equals the first supplied cashflow date. Count elapsed days to settlement, excluding the settlement date from the accrual interval. On a coupon date the caller must reset last coupon to that date and provide future flows. `ACT360` is actual/360, **not 30/360**. This is a declared simplified convention, not an inferred security convention.

The two-year annual example with 1000 par, 50 then 1050 paid on exact 365-day intervals, and 5% annual yield values at 1000. With independently supplied accrued interest of 20, its clean value is 980. Unsupported: callable/putable/convertible, floating or inflation-linked, default recovery, uncertain or negative cashflows, amortization schedule generation, ex-coupon negative accrued interest, accrued-at-settlement entitlement exceptions, yield-curve bootstrapping, duration/convexity and credit spread inference. Existing separate bond tools may provide other calculations; this operation does not replace them.

## Fixed futures position: `futures_pnl`

Exact inputs: `signed_contracts` (nonzero integer from -1 billion to 1 billion; long positive), `multiplier` (positive underlying units per contract, or currency per price point where the price unit is a point), `price_unit` (such as `USD/barrel` or `USD/point`), `entry_at`, `entry_price`, `settlements` (1–10000 `{at,price}` objects), `fees` (nonnegative total currency amount), `settlement_method: "variation_margin"`, `rounding` (`unrounded_research` or `per_contract_half_up`), `currency_decimals` (integer 0–8), and `terminal_state` (`open`, `closed`, `cash_settled`, or `physical_delivery_pending`). Envelope currency must match the price unit prefix. Entry and settlement prices can be positive, zero or **negative**. Entry and settlement timestamps must be explicit aware instants. First settlement can share the entry instant; subsequent instants must strictly increase. Every entry/settlement instant must be at or before `inputs_available_at`, hence at or before the information cutoff. This operation is a supplied observed settlement ledger, not a projected scenario path; date-only values and future observations are rejected. Future **contractual bond cashflow dates** are allowed because they are projections, not settlement-price observations.

For a constant position, each variation payment is quantity times the difference between successive per-contract monetary values. Sum of the ledger is gross P&L; net P&L subtracts supplied total fees once. `per_contract_half_up` uses an isolated 50-digit Decimal context with explicit exponent bounds and traps, then decimal arithmetic to round `price*multiplier` separately at each mark before differencing, with ties away from zero; `unrounded_research` applies no monetary rounding and ignores `currency_decimals` numerically while retaining it in the contract. Verify the actual contract's rounding rule before reconciliation: special notional-product rounding is unsupported.

The example holds two contracts, multiplier 1000, entry 10, settlements -5 then -10: variation payments are -30000 and -10000, gross -40000, net -40012 after fees of 12. `terminal_state` is supplied descriptive metadata; `closed`/`cash_settled` means the last supplied price is asserted by the caller to be the exit/final mark. No order, exchange settlement or delivery is performed or verified. Physical delivery remains uncompleted. This covers a fixed linear contract position with no rolls, adds, partial exits, inverse crypto contract formula, spot-quoted financing adjustment, interest on margin, margin account/funding model, margin call, contract eligibility or delivery cost.

## Example prompts

- “Using `derivatives-american-option.json`, value the fictional American put. Show the continuous dividend assumption, per-unit premium and grid limitation. Repeat at 400 steps and report the difference; do not call the first result converged.”
- “Invert the premium in `derivatives-implied-volatility.json`. Report status, initial bracket, residual and implied decimal volatility if converged. Do not infer volatility at expiry or turn a flat price into a unique estimate.”
- “Compute the supplied USD/EUR covered-interest forward in `derivatives-fx-forward.json`. Explain its quote orientation and missing basis adjustments. Do not present it as expected future EUR/USD.”
- “Price the complete fictional bond cashflows in `derivatives-bond-cashflows.json`. Show dirty, accrued, clean and price per 100. Identify the supplied discount and accrual conventions rather than inferring a Treasury convention.”
- “Reconcile `derivatives-futures-settlement.json` across the negative settlement prices. Show each variation payment and total fees. State that physical delivery remains pending and no broker action occurred.”

## Method attribution and code provenance

All implementation and test code is newly written for this project. No source code, diagrams or document text were copied from third parties; no new dependency or bundled third-party asset is introduced. Mathematical methods are attributed here; these references are not code licenses and do not grant permission to redistribute their documents.

- Cox, Ross and Rubinstein, *Option Pricing: A Simplified Approach*, Journal of Financial Economics 7 (1979), 229–263, [original paper](https://bpb-us-w2.wpmucdn.com/u.osu.edu/dist/7/36891/files/2017/07/CRR79-1yy8av8.pdf), [publisher DOI record](https://www.sciencedirect.com/science/article/pii/0304405X79900151). The continuous-yield tree above applies the risk-neutral carry `r-q`; American backward exercise uses the same optimal-stopping principle.
- BIS, [Covered interest parity lost: understanding the cross-currency basis](https://www.bis.org/publications/qr-201609/covered-interest-parity-lost-understanding-cross-currency-basis), especially Box A. Supports quote orientation and why real market forwards may deviate from idealized parity.
- FINRA, [Bonds](https://www.finra.org/investors/investing/investment-products/bonds), pricing and accrued-interest sections, and [accrued-interest calculator](https://accruedinterest.nga.finra.org/calculator/). Supports separating quoted price from accrued interest; this toolkit declares its own limited ACT365F/ACT360 calculation rather than claiming general market convention coverage.
- CME Group, [Money Calculations for CME-cleared Futures and Options](https://www.cmegroup.com/clearing/files/CME-Money-Calculations-Futures-and-Options.pdf), normal per-contract monetary rounding and variation sequence; [profit/loss calculation](https://www.cmegroup.com/education/courses/introduction-to-futures/calculating-futures-contract-profit-or-loss). The toolkit does not implement every product-specific exception in CME's document.
