# Official Robinhood integration contract

This review did not authenticate to an account or place orders. No Robinhood MCP
tools were connected in the review environment. Live account behavior remains
untested; never describe the package as production-certified.

Robinhood documents account/portfolio/quote tools and equity review/place/status
operations in [Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/).
Inspect the actual connected tool schemas at runtime. Documentation names are
discovery hints, not an assumed API schema or permission grant.

## Capability discovery

Verify eligible account routing, approval setting, asset/order/TIF support, quote
timestamps, tick/quantity increments, broker review, cumulative order status,
cancellation semantics, tax-lot reads and protection/exit capabilities. Capture
capability evidence and its check time. Do not claim native OCO/brackets merely
because independent stop orders are available.

Map the user's account alias to exactly one broker-designated eligible Agentic
account. Never silently pick another account after reconnect. Account numbers and
auth material stay inside the trusted broker tool/runtime. Only a sanitized alias
enters helper files and reports.

## Runtime bridge

The Codex execution stage supplies normalized inputs and invokes the official MCP
tools; the Python modules intentionally contain no undocumented Robinhood HTTP
client. The sequence is:

    read account/positions/quotes/orders -> reconcile -> normalized snapshot
    exact order -> risk_engine.evaluate -> official broker review
    permission/protection check -> ExecutionLedger.claim
    official order submission exactly once -> broker status -> ledger.reconcile

Use tools available in the current session. Do not install a third-party credential
wrapper, scrape order screens, or bypass the official interface. A missing tool,
mandatory broker approval or unsupported instrument produces a blocked/proposal
result. Broker capability flags in local JSON must come from observed evidence.

An order write can time out after acceptance. Never retry automatically. Fetch
orders/history and match the intent; if matching is ambiguous, retain UNKNOWN and
halt entries. Read-only retries may use bounded backoff. One writer must own the
account journal. SQLite serializes local claims, but does not stop other software
or manual broker actions; reconcile those before continuing.

Broker trade approvals may require the user to act in Robinhood even if the local
mandate permits the order. Never alter that setting in this workflow.

## Session, settlement and margin

Supply actual session open/close timestamps from broker/exchange calendar data,
including holidays, early closes and daylight-saving transitions. No hardcoded
weekday or 4 p.m. check substitutes for the calendar. Restrict this runtime to
regular U.S. equity sessions. Protect against future timestamps and clock drift.

Use settled cash and current broker buying power as distinct values. Pending sales
do not fund new orders. The SEC adopted T+1 for most broker-dealer transactions;
actual settlement and restrictions must come from the broker, not an inferred
calendar-day increment. See [SEC settlement rule](https://www.sec.gov/rules-regulations/2023/02/34-96930).

As researched October 6, 2026, Robinhood states that its day-trading framework moved
to intraday margin standards on June 4, 2026. FINRA permits firm transition through
October 20, 2027. Do not hardcode the historical $25,000 PDT rule or assume every
broker/account uses the same implementation. Read account restrictions and current
maintenance requirements. The shipped runtime remains unlevered and uses cash caps.
Sources: [Robinhood day trading](https://robinhood.com/us/en/support/articles/pattern-day-trading/),
[FINRA transition guidance](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements).

## Required live integration evidence

Before activation demonstrate actual normalized snapshots, order preview, approval
behavior, route correctness, state reconciliation, persistent signal deduplication,
protection/time exits, outage handoff and a separate kill switch. Test failures with
a broker sandbox if available or recorded/mocked fixtures; do not invent a Robinhood
paper endpoint. A funded live test requires its own explicit authorization.

## Executable schema mapping in v3

broker_bridge.build_request accepts only the official endpoint, verified local
account alias, fresh connected_official_mcp_schema_observation and a matching
schema hash. Operations include account/positions/orders/quote/review/submit/
cancel/advanced_review/advanced_submit. Names are internal roles; each maps to an
actual observed tool name and schema, not an invented HTTP endpoint.

Bindings map actual argument names to {pointer,type}. Supported exact conversions
are string/integer/number/boolean/raw. Nested arguments use {object:{field:binding}}
or {array:[binding,...]}. enum_map is allowed only for side/order_type/time_in_force
with observed evidence. It cannot translate quantity or price to different values.
Resolve any external JSON-schema refs into a local schema first; no implicit fetch.

Required economic mappings include symbol, side, quantity, limit_price, order_type,
time_in_force and extended_hours. If a tool fixes one of the last three, supply
fixed_semantics[field]={value,evidence}; it must exactly match the order. Do not
assume DAY or regular session from an omitted argument. Account identity must bind
private_routing or an evidenced connection_scoped_account with the same alias.
Cancel must bind /private_routing/broker_order_id to the verified local target.

Advanced entry also maps /order/stop_price and /order/target_price and needs observed
protection_semantics: atomic_with_entry, partial_fill_quantity_tracking,
mutually_exclusive_exits, all true with evidence. Real child TIF/quantity semantics
and expiry must match the entire holding window. A boolean in a hand-written
template is not proof that the broker implements these guarantees.

Request preparation alone never authorizes execution. Keep actual arguments in
host memory and persist only hashes/redacted reports. redact_request handles nested
private routing. The host performs the MCP call after a valid ledger claim; the
Python bridge has no OAuth client or network order path. Query broker status and
normalize cumulative fills/average price excluding fees. Impossible limit-price
fills keep the intent unresolved for investigation.

The advanced tools documented by Robinhood do not, by their name alone, establish
the required protection semantics. If discovery cannot verify them, record exactly
which capability is missing and retain paper/proposal operation for that route.
