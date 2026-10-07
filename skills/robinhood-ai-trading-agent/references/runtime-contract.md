# Runtime contracts

Python 3.11+. Monetary gates/journal use the standard library; personal readiness also uses the dependencies in requirements-tested.txt.
Examples are executable fictional fixtures. They are not broker snapshots or user
authorization. Decimal inputs can be JSON strings; output monetary values are strings.

## Policy

For personal use see [personal-policy.example.json](../templates/personal-policy.example.json), schema 3. policy.example.json remains the schema-2 offline learning fixture. Fractions use 0.05 for
5%, not 5. Sleeve caps and core target weights use total account equity. The sum of
sleeve caps plus cash floor cannot exceed 1. Per-trade and open-risk fractions also
use total equity; day/week loss limits use their respective starting equities.

mode is paper/approval/bounded_autonomous. deployment_context is learning/personal.
Live claims require schema 3, personal context, approved configuration, actual human authorization and personal readiness. Learning context independently rejects live claims. This field is an operational interlock, not a security
boundary against local file modification.

live_validated_setups is empty by default. Promotion requires evidence and explicit
policy approval. allowed_setups controls research/paper candidates; it does not
promote a strategy to live. Allowed symbols are an explicit universe, not a scanner's
unverified output. setup_sleeves maps every allowed setup to permitted sleeves;
changing a core setup's label cannot make it an intraday strategy.

## Snapshot

[snapshot.json](../examples/snapshot.json) shows all required fields:

- account_alias: user-chosen label resolved by the trusted broker stage.
- as_of: actual observation timestamp; timezone required. Never refresh a cached
  quote/account merely by relabeling its time.
- equity: marked long-only account equity; cash + sum(quantity * mark) must reconcile.
- cash: gross cash ledger balance; settled_cash: settled portion. Neither is future
  sale proceeds. Open buy reservations are subtracted by this helper. buying_power
  is current broker available buying power and is not treated as a leverage allowance.
  If a provider supplies net cash fields, normalize to gross or block; do not subtract
  reservations twice by accident or silently add unsettled money.
- positions: one row per symbol/sleeve, with quantity, mark, sector, asset_type and reviewed issuer_id; tactical rows need stop_price and exit_by. Marks must be refreshed with the account snapshot. Unknown manual
  ownership must be reconciled before declaring reconciled=true.
- open_orders: all relevant account orders, including protective orders. Each row
  has unique local_ref, status, symbol, side, sleeve and remaining_quantity. Buys
  also need reservation_price, sector, asset_type, issuer_id and tactical stop_price. Cancellable targets need role=entry/protection. Remaining quantity
  excludes cumulative fills already in positions. Cancel-pending still reserves.
  Unknown/unbounded market-order reservations block normalization and entry.
- day/week_pnl_ex_flows: marked P&L excluding deposits/withdrawals, not realized-only
  P&L. Corresponding starting equities must be known. flow_adjusted_equity and
  flow_adjusted_high_water_equity must be on the same cash-flow-normalized scale.
- agent_tradable, restricted, maintenance_deficit, reconciled,
  risk_metrics_verified, kill_switch: verified state, not optimistic defaults.
- session: is_trading_day and official open/close timestamps for this U.S. regular
  session. Use real calendar evidence, including early closes and DST.
- quotes: broker-observed asset_type (equity/etf), bid/ask/as_of/tick_size/tradable/halted/sector,
  average_daily_dollar_volume and event_clear per requested symbol. Personal quotes also require source=official_broker, real_time=true, leveraged_or_inverse=false for buys, and reviewed issuer_id. event_clear
  means the relevant event calendar and user exclusion policy were actually checked.
  Asset type must match the proposal; never let the proposal itself choose an ETF cap.
- reconciled_through_intent: latest local completed intent ID, set only after a new
  broker reconciliation. Required by the ledger once any previous intent exists.

Broker state changes between preview and submission can still cause rejection.
Local gates cannot make a distributed broker transaction atomic.

## Exact order

[order.json](../examples/order.json) shows the supported shape. id is a unique intent;
signal_id is stable across polls/restarts for a setup version, symbol, signal time
and action. Both deduplicate. A new retry ID must not sidestep the signal key.

asset_type is equity/etf; side is buy/sell; sleeve is core/swing/intraday. The current
helper supports whole-share DAY limit orders with extended_hours=false. It validates
tick increments, distance from current quote, freshness and expiry. Tactical buys
require stop_price, target_price and exit_by. Intraday exit_by must precede the
official close. Core buys must fit the symbol's approved core target.

The replay's daily trend has no target exit. Before mapping it to the current
tactical order gate, define a target/risk criterion in the registered live strategy
or extend/test the schema explicitly; do not fabricate a target to make it pass.

## Broker review and authorization

review contains order_hash, snapshot_hash, checked_at, official_mcp, accepted,
supported_order, trade_approvals_enabled, warnings, and exit_plan_verified for
tactical buys. Hashes use risk_engine.canonical_hash. Actual observed broker/host
evidence supplies all flags; a manually edited true is not capability evidence.

An authorization has id, kind (order/mandate), policy_hash, account_alias, starts_at,
expires_at and human_authorization_ref. Exact-order grants additionally bind
order_hash and review_hash. The host verifies human intent before calling authorize.
The helper itself is not an identity provider.

    ledger = ExecutionLedger(path_to_durable_db)
    # Host verifies the human instruction before recording authorization.
    ledger.authorize(actual_human_grant)
    claim = ledger.claim(policy, snapshot, exact_order, review, grant_id)
    # Only the trusted personal execution stage may map a permitted claim to MCP.
    # The personal Codex host calls the observed authenticated MCP tool once.
    ledger.reconcile(intent_id, broker_state, cumulative_filled, average_price)
    ledger.close()

Use one durable live database per account alias across approval and bounded modes;
their daily counters are shared. Keep paper fixtures in a separate database. Mode
switches are not a reason to start a new live database or reset counters. Authorizations are immutable; revoke then create a new
record. Exceptions are blocked results, not permission to skip checks.

## Replay bars

CSV columns: timestamp, session_open, session_close, open, high, low, close, volume.
timestamp denotes completed-bar end. Offset-bearing times are mandatory. Intraday
example uses 5-minute bars; daily example uses one regular-session close per day.
Real data must be audited upstream for exchange calendar gaps and corporate actions.
The helper rejects invalid OHLC, duplicates and flagged interpolated rows. It does
not supply market data or prove the authenticity of a CSV.

Replay trade timestamps describe signal/bar boundaries, not tick-level fill times.
OHLC cannot identify the actual intrabar execution time. Open residual positions
are marked at the last close and reported explicitly.

## Version 3.0 compatibility

Personal live claims require schema_version=3 and the personal policy fields. Schema 2 remains usable for offline examples but cannot bypass personal readiness. Old incomplete inputs fail closed. Reapprove changed policies and restart their supervised session with the new hash; do not silently amend grants.
Existing ledger tables remain readable. Contradictory terminal updates now persist
UNKNOWN and a conflict event before raising, keeping subsequent claims blocked.

Research settings, candidate manifests and price-audit records are separate from
execution authorization. No helper automatically turns research Eligible or a
GARCH flag into event clearance, an order or a live strategy promotion.

## Additional personal evidence

The snapshot must include session_activity_reconciled=true,
external_session_order_count and external_session_turnover, derived from broker
session history excluding already matched local claims. Count external parent
attempts and actual child executions consistently; never double count OCO alternatives
as executed turnover. Local claimed attempts remain conservatively reserved in
daily budgets. Missing external/manual activity is not zero. After a cancellation,
reconciled_through_cancellation names the last cancellation intent only once new
positions, fills and working orders were checked.

review.readiness_inputs contains:

- Exact snapshot_hash/order_hash; capabilities and broker_inputs (order plus
  host-private routing); reviewed_request_hash of the actual submit request.
- session_owner matching the durable account session lease.
- events: symbol/source/checked_at/coverage_verified/coverage_start/coverage_end/events.
  Each event has kind/earliest_at/latest_at/evidence; use a credible whole interval
  for unknown times. Coverage includes lookback/release and future pre-event windows.
- protection: native observed groups with symbol/sleeve/protection_ref/state,
  native_broker, side=sell, covered_quantity, actual stop_price, expires_at and as_of.
  Working coverage must match the position's planned stop and extend through exit_by.
- new_protection_valid_until and new_protection_evidence for tactical entries,
  corroborating child expiry beyond the planned holding period.
- issuer_mapping_verified, fund_holdings keyed by symbol with as_of/evidence/holdings.
  Holdings have symbol/asset_type/sector/fraction/issuer_id. Explicit USD cash uses
  asset_type=cash and symbol=USD; missing fractions remain UNKNOWN. Issuer IDs join
  direct holdings and multiple share classes. No caller-supplied projected prices
  are used: exposure is derived from snapshot marks, reservations and the new ask/limit.
- Core stock candidate in screen_review's schema plus candidate_checked_at. Core
  ETF fund_review instead contains symbol and mandate_fit/fees_tracking/
  structure_liquidity/holdings_concentration, each with status=pass and evidence.
- garch: the complete emitted result with actual audit/run hashes and matched
  symbol/frequency. An optional supplied eligible model is still validated.
- portfolio_returns, when required: data_kind=market, audit_passed, input_hashes,
  return_definition=daily_simple_total_return and returns keyed by symbol containing
  timestamp/return rows. Weights are computed from projected exposure, never supplied.
- strategy_evidence: retained market/forward-paper report satisfying the setup's
  versioned criteria and approved_report_hash. No bundled strategy is promoted.

All evidence values originate in actual observed sources. Complete JSON, a hash
or a true flag is not independent proof. Local operational gates assume a trusted
host following these rules; they cannot defend against deliberate database/code edits.

## Cancellation actions

claim_cancel(policy, snapshot, action, review, authorization_id) reserves a single
cancel request in a separate durable table. action carries id,target_ref,account_alias,
symbol,sleeve,role. review binds snapshot_hash, actual official evidence, acceptance,
approval setting, checked_at, warnings, session_owner, capabilities, broker_inputs,
reviewed_request_hash and target_identity_verified. broker_inputs.target_ref must
resolve privately to exactly the observed broker_order_id.

An actual cancel-preview tool is not assumed. Cancellation review means verified
target/status/permissions and the discovered schema; never fabricate a broker
preview response. For protection, reduction_plan specifies matching symbol/sleeve,
purpose=reduce_owned_position, gap_risk_acknowledged=true and human_handoff_ref.
Mandates need explicit permissions cancel_entries/cancel_protection_for_reduction;
otherwise bind an exact action and review with a one-time grant. Rejections/warnings
or expired authority block submission.

reconcile_cancel(action_id, target_state, evidence_ref) records the actual target
order status. A rejected cancellation request is NOT a REJECTED target order;
the still-working target remains OPEN/UNKNOWN. Only terminal target evidence
releases the cancellation latch. Fill changes remain accounted in the entry journal
and fresh broker snapshot. Protective cancellations do not rewrite a FILLED parent
entry into CANCELLED. Replacement/reduction orders use new exact claims.

## Current signal binding

Live tactical orders also carry setup_version and signal_at. signal_evidence has
symbol, data_kind, source, audit_passed, exact bars_hash and bars containing
timestamp/open/high/low/close/volume (completed bar ends). The bundled live signal
adapter recomputes opening_range_breakout from a complete current-session grid,
rejects unfinished/stale bars, and verifies stop/target/entry limit against that
signal. Stops round up and targets/entry caps down to the observed tick.

The registry records signal_parameters (opening_bars/bar_minutes), a combined
implementation_sha256 for strategy_lab.py + signal_review.py, and
max_entries_per_symbol_session. Strategy evidence binds that code and parameters
hash as well as the registered version. Updating code/rules requires renewed
validation and authorization. external_setup_entry_counts maps setup:symbol to
unmatched broker entry counts; together with local attempts it enforces the
session cap. Cancelled attempts conservatively consume an entry allowance.

The included daily SMA is a research baseline with no live adapter: it has no
target exit matching the parent/protection contract. It must be extended and
evaluated as a new strategy before live promotion. Core long-term allocation uses
its separate fundamental/fund review and does not need an intraday signal.
