# Exact-order approval and bounded mandates

## Permission records

An order grant binds immutable order, broker-review and policy hashes, account alias and validity interval to actual human approval. It is consumed once even if submission fails. Changed parameters require a new review and grant.

A mandate binds the entire policy hash, account alias, validity interval and a reference to the human instruction. Policy includes symbol/setup allowlists, promoted strategies, sleeves, core targets, order/turnover caps, risk limits and hours. Every order still receives fresh risk and broker reviews. Policy changes, expiry, revocation, warnings or unsupported capabilities close the gate.

Prepare [autonomous-mandate.md](../templates/autonomous-mandate.md) before requesting activation. A request to build an autonomous agent does not specify unknown capital or broker capabilities. Once a concrete mandate is approved, do not ask again for each compliant trade. Broker-required approvals still apply.

ExecutionLedger.authorize stores a host-verified human decision; it does not authenticate a person. A research/model process must not manufacture grants. Host tool permissions enforce that boundary.

## Submission procedure

1. Resolve previous intents against broker state. All local intents must be terminal; incomplete ones serialize further writes. After comparing actual positions and open orders, refresh the snapshot and set reconciled_through_intent to the last local intent.
2. Construct one exact order with stable intent ID, timestamps, account alias and sleeve/setup. The host must deduplicate originating signal keys across polls; do not create new IDs for the same signal.
3. Run deterministic gates plus reasoning review. Inspect actual MCP schemas and obtain broker preview. Bind review to order and normalized snapshot hashes.
4. Verify grant and exit coverage. Call ExecutionLedger.claim from the single account writer. It atomically checks permission, unresolved intents/cancellations, duplicate ID/hash, account-wide daily counters, risk and personal_readiness (including the active session, event/model/strategy and portfolio evidence).
5. Only with may_submit_once=true, send exactly this order once through the official broker tool. Use broker_bridge and verify broker_request_hash against the prepared actual MCP request. Recheck freshness/lease/revocation immediately before dispatch; do not regenerate arguments from prose.
6. Record status and cumulative filled quantity/average price. CLAIMED after crash and UNKNOWN after timeout are unresolved, not retry permissions. Query broker history using the host's restricted mapping and exact attributes.
7. Confirm terminal status, refresh account state, then journal. CANCEL_PENDING is not cancelled; a partially filled cancelled order still owns its filled shares.

The ledger intentionally permits one nonterminal local intent at a time. Native protective orders must also appear in the snapshot. The broker must supply native atomic protective orders and exclusive exits. The bridge verifies observed schema semantics; the local journal manages permission, cancellation/reconciliation and replacement claims. It does not emulate an exchange or provide an unattended daemon.

## Protection and exits

A stop_price is a sizing assumption, not a child order. Set review.exit_plan_verified=true only after verifying actual broker protection and the approved time-exit mechanism. Reconcile child quantity after partial fills. Never submit independent stop and target orders that could both fill into a short position: use verified native OCO or serialized monitored exits.

If native atomic, partial-fill-aware protection is unavailable, keep live tactical entry blocked. The supervised session supplements native protection with time-exit and outage handoff; it cannot guarantee stop enforcement or latency. Follow personal-setup.md. Both approval and bounded modes require validated tactical evidence.

## Recovery

- Kill switch blocks entries but permits authorized risk reductions. Cancel entry orders only if authorized and verify final cancellation.
- Grant revocation stops further automated submissions; it does not cancel broker orders or liquidate holdings. Report and hand off existing risk.
- Session counters include all local claimed attempts plus reconciled external/manual broker activity. Turnover includes gross buy/sell claimed notional and unmatched broker activity; entry caps do not block authorized reductions.
- Contradictory terminal updates persist UNKNOWN plus a conflict event before raising.
  They keep subsequent claims blocked across restart until authoritative reconciliation.
- Live daily counters aggregate approval and bounded-autonomous claims in the same
  account journal; changing mode cannot reset the daily budget.
- Back up SQLite using its backup API. Do not reset the database to clear a breaker or stuck intent.

## Cancellation and time exits

Use ExecutionLedger.claim_cancel before the exact official cancel call. One cancel
intent remains unresolved through ACK/CANCEL_PENDING, so new orders cannot race it.
Only terminal target evidence completes reconcile_cancel. Re-read fills, positions
and protection, mark reconciled_through_cancellation, then create a fresh risk-
checked reduction/replacement order. See runtime-contract.md for required fields.
Never consume a one-time grant for both a cancellation and a replacement. A bounded
mandate must explicitly permit the cancellation role and the subsequent reduction.
