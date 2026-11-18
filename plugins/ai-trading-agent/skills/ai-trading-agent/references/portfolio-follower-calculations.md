# Portfolio follower calculations

`scripts/portfolio_follower.py` provides two pure functions, `build_targets(document)` and `rebalance(document)`. They operate on supplied, normalized evidence. They do not fetch websites, monitor on a schedule, transmit broker orders, predict returns, or establish whether a public figure is worth following. Refresh sources on demand and preserve the original evidence and first-availability clocks. Public-source normalization is documented separately in `portfolio-disclosure-inputs.md`.

The supported model is a long-only, USD, common-stock follower allocation with several explicitly budgeted sleeves. A 13F basket is the reported eligible common-stock basket, **not** the manager's full portfolio or cash allocation. Options, shorts, private assets and undisclosed holdings are excluded and labeled unknown. A trade disclosure's dollar range is never converted into an actual allocation by choosing its midpoint. A political disclosure, celebrity recommendation and manager snapshot are different evidence types.

## Target input contract

Required document fields:

| Field | Meaning |
|---|---|
| `as_of` | Decision timestamp with timezone, ISO 8601. |
| `currency` | `USD`; other currencies are currently unsupported. |
| `max_position_weight` | Positive fraction, at most 1, capping aggregated follower targets as a fraction of whole-account NAV. It does not purport to cap unrelated positions. |
| `sleeves` | Nonempty list with unique `id` values. |

Every sleeve requires `id`, `subject_id`, `mode`, `budget_weight`, `current_weights`, `source_status`, `checked_at`, `max_age_days`, and `records`. `mode` is `snapshot`, `events`, or `inverse`. Budget fractions must be positive and sum to at most 1. `current_weights` maps security IDs to the existing follower target **within that sleeve**, with nonnegative weights summing to at most 1. An empty mapping means no existing follower position is attributed to this sleeve; never silently replace an unknown baseline with empty holdings. Baselines must come from reconciled follower state, not the followed person's presumed allocation. These weights describe intended holdings; actual shares are separately reconciled by `rebalance`.

Only `source_status: "verified"` enables new source-driven targets. Any other status preserves the baseline. A source check older than `max_age_days` has the same result. `checked_at` cannot be after `as_of`. Refreshing the check date does not refresh an old economic signal: event modes discard signals whose **`event_at`** is more than `max_age_days` before `as_of`; if all records for a security expire, that security is frozen at its baseline. A snapshot uses its holdings period end as `event_at` and the same age limit. Choose a stated policy suitable for the disclosure lag; do not change the limit merely to make an expired signal actionable.

Every record requires:

| Field | Meaning |
|---|---|
| `subject_id` | Must exactly match its sleeve. Use stable source/entity IDs rather than a guessed person's identity. |
| `event_id` | Stable source event identity, unchanged across corrections. |
| `revision` | Integer, zero or greater; highest available revision wins. |
| `withdrawn` | Explicit boolean. A withdrawal never resurrects an older version. |
| `source_ref` | Nonempty retained public source reference. Verification is the adapter/researcher's responsibility. |
| `event_at` | Economic event/recommendation time, or snapshot period end. |
| `published_at` | Public publication timestamp for this revision. |
| `available_at` | First time this exact revision was available to the decision process. Preserve it across repeat downloads. |

Clocks must satisfy `event_at <= published_at <= available_at`. Only revisions available at or before `as_of` participate. Repeated identical rows are idempotent. Different payloads at the same event ID and revision freeze that sleeve instead of guessing which is right. Publication and availability dates must not be backdated to the trade or quarter end. This engine does not claim that a modern model's interpretation recreates historical knowledge.

### Snapshot records

A snapshot adds `currency: "USD"`, `complete_reported_basket: true`, and `positions`. Each position has `security_id`, `asset_type`, `eligible_common`, and `market_value`. Only `asset_type: "common_stock"` and `eligible_common: true` participate. `market_value` is a nonnegative number or decimal string in the snapshot's single stated currency; normalize source units before using it. Duplicate security IDs are aggregated. Values must represent the complete eligible reported common-stock basket, including resolved identifiers; do not mark an incompletely parsed/mapped basket complete. Missing assets outside the public filing are still unknown, even when the reported common-stock basket is complete.

The latest available period-end snapshot supplies normalized basket weights `value / sum(eligible values)`. Multiple different snapshot IDs at the same latest period end, a withdrawn latest snapshot, an incomplete snapshot, an expired snapshot, no available snapshot or an empty eligible basket preserves existing positions. There is no fallback to an older unwithdrawn snapshot. An observed empty filing alone is insufficient evidence to exit an existing portfolio with this conservative implementation.

### Event and inverse records

These sleeves additionally require `allocation_policy`, `partial_sell_policy`, and, for a user-weight policy, `user_weights`.

`allocation_policy: "user_weights"` uses an explicit mapping of security IDs to within-sleeve target fractions. This is required for ordinary `events` and is supported for `inverse`. `inverse` also supports `allocation_policy: "active_equal"`, which distributes the remaining sleeve allocation equally over active, unfrozen long positions. Frozen weights remain at their baseline. Ordinary event allocations that exceed the sleeve budget raise an error; the engine never silently funds them by leverage.

Records add `security_id`, `action` (`BUY` or `SELL`), `eligible_common: true`, `qualifying: true`, and, for disclosed sales, `sale_scope` (`full`, `partial`, or `unknown`). Eligibility and qualification must explicitly be true to act. The engine expects classification from verified source evidence, not an unexamined quotation or ambiguous headline.

For ordinary events, a BUY sets the configured user target. A SELL with `sale_scope: "full"` clears the follower target. A partial sale clears it only if the explicitly selected `partial_sell_policy` is `exit`; the `hold` policy preserves it. Unknown sale extent always preserves it. Partial percentage reduction is not inferred from disclosure amount ranges. Partial reduction by a known percentage is outside this implementation's current scope.

For long-only inverse recommendations, a qualifying SELL activates a long target and a qualifying BUY clears that follower target. It never opens a short. BUY calls on securities not held by the follower do not sell unrelated account shares. Inverse calls describe recommendations, so ordinary disclosed-sale scope does not reinterpret their meaning. The required `partial_sell_policy` belongs to the shared input contract and does not turn a recommendation into a transaction.

Events are ordered by economic event time after selecting available revisions. Conflicting actions, withdrawal status or sale scopes at the same time for the same security freeze that security. Any nonexpired withdrawn event also freezes that security. This intentionally avoids guessing how to reverse a historical action; reconcile the baseline and corrected event history before retrying. A frozen security shared by multiple sleeves prevents all new trades in that security, including otherwise fresh overlapping signals.

### Aggregate targets

For security `i`, aggregate `sum(sleeve_budget * within_sleeve_weight_i)` and cap at `max_position_weight`. Overflow stays in cash; it is not redistributed. Unassigned sleeve budget also stays in cash. Output includes `target_weights`, `target_cash_weight`, `cap_overflow_cash_weight`, per-sleeve attribution, source limitations, `scope_security_ids`, and `frozen_security_ids`.

These are **nominal pretrade targets**. Frozen holdings can remain above a nominal cap, and cash, unrelated positions, costs, minimum trades or rounding may prevent targets from being attained. A target is not an executed position or an estimate of the followed investor's complete allocation.

## Rebalance input contract

`rebalance` accepts a `target_document` with the contract above and these additional required fields:

| Field | Meaning |
|---|---|
| `currency` | `USD`, same account currency. |
| `holdings_at`, `max_holdings_age_seconds` | Freshness bound for the current holdings ledger. |
| `holdings` | Unique security rows containing `security_id`, total long `quantity`, and attributed `follower_quantity`; `0 <= follower_quantity <= quantity`. |
| `quotes` | Mapping for every held security and every nonzero target security. Each quote requires positive `price`, positive `quantity_step`, `price_basis: "unadjusted"`, `source_ref`, `observed_at`, `available_at`. |
| `max_quote_age_seconds` | Maximum elapsed time since quote observation; quotes must be observed before availability, and available by decision time. |
| `account_nav` | Reconciles within $0.01 to settled cash + pending receivables + total held quantities times quotes. Must be positive. |
| `settled_cash`, `pending_receivables` | Nonnegative USD amounts. Receivables affect NAV but cannot fund buys. |
| `cash_floor`, `reserved_cash` | Nonnegative amounts protected from purchases. Reserved cash cannot exceed settled cash. Include any chosen tax reserve here; the engine does not estimate tax liability. |
| `open_orders` | Must be `[]`. Reconcile fills/cancellations outside this calculation before proposing another rebalance. |
| `fixed_fee_per_trade`, `cost_bps`, `min_trade_notional` | Explicit nonnegative cost and trade-size assumptions. Cost rate must be less than 100%. |

Shorts, margin, multiple currencies, liabilities, leverage, corporate-action processing, tax-lot optimization, authentication and orders are not supported here. Use the separate holdings/accounting facilities to establish correct current quantities and adjusted historical records. Quotes for execution proposals are current unadjusted prices, not historical total-return-adjusted prices.

The target follower quantity is whole-account NAV times target weight divided by quote price. Only `follower_quantity` is considered for reductions; unrelated quantities are untouched, including unrelated shares of the same ticker. Previously attributed follower holdings absent from the current scope are preserved and reported for reconciliation. This prevents an absent/deleted profile from becoming a liquidation signal.

Sell quantities round down to the declared quantity step and cannot exceed follower holdings. Trades below minimum notional are omitted. Sales whose modeled cost consumes their entire proceeds are deferred. **Proposed sales and pending receivables never fund buys.** They remain separately reported as estimated unsettled proceeds until a later refresh reconciles actual settlements.

Available purchase cash is `max(0, settled_cash - cash_floor - reserved_cash)`. Desired buys are scaled proportionally after reserving one fixed fee per desired buy. The remaining amount funds price plus basis-point costs. Each scaled quantity rounds down; too-small trades are omitted, and leftover rounding cash is not redistributed. Consequently the method is deterministic and conservative, rather than claiming an optimal execution schedule. Fee/slippage assumptions are estimates, not guaranteed fills.

Output separates targets, feasible `proposals`, `deferred` reasons, estimated cash use, cash-floor shortfall, and estimated unsettled sale proceeds. It does not call a broker or attest that orders executed. A cash floor already breached is reported; proposed sales do not falsely repair settled cash immediately.

## Fictional arithmetic check

The example has $1,000 NAV: $200 settled cash, $100 pending receivables, ten AAA shares at $50 and ten OUT shares at $20. Six AAA shares belong to this follower; four AAA and all OUT shares are unrelated. An observed full exit of AAA and purchase signal for BBB set a 50% whole-account BBB target. BBB costs $25, the cash floor is $50, and each trade costs $1 plus 1% of notional.

The proposed sale is **six** AAA shares: $300 gross, $4 modeled cost, $296 estimated unsettled proceeds. It does not sell the other four AAA shares or OUT. The BBB intention is twenty shares, but only $150 is spendable; the feasible proposal is **five** BBB shares: $125 gross plus $2.25 costs. Settled cash would be $72.75 if those buys fill. Neither the $100 receivable nor the $296 proposed sale proceeds fund those buys. The example is fictional and is not a suggested allocation.

Run `python scripts/portfolio_follower.py examples/portfolio-following.json`. The JSON envelope uses `operation` and `inputs.document`; the host's workbench can expose the same pure functions. `tests/test_portfolio_follower.py` checks this arithmetic independently, clock/revision behavior, inverse direction, expiry, conflicts, overlap/caps, ownership scope and settlement constraints.
