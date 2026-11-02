# Broker handoff

The skill researches and recommends; the host's connected broker tools perform
requested transactions. There are no skill-level execution gates. Preserve the
user's current instructions and authority without requiring another policy,
strategy, grant, ticket, volatility test or skill approval.

Robinhood's [Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
describes available capabilities. Actual connected tool schemas and responses
are authoritative for that host/account; documentation is a discovery aid. Do not
invent an approval-setting tool or require an unavailable preview field. If review
and submission schemas differ, map their actual economic fields rather than
assuming identical arguments or a broker-provided request hash.

## Orders and amounts

Pass the user's instrument, side, amount/quantity and order preference to the host.
Use market execution as the handoff preference when an investment instruction
omits the order type; preserve an explicit limit. Discover actual support for
fractional quantities, native dollar amounts, TIF and sessions. Do not silently
replace an unsupported order with different economics.

Native dollar input may be converted into shares using a recent trade price.
The final market fill and fees can differ from the submitted dollar value. Report
actual fills and costs; a local amount is not proof of a broker-enforced debit cap.
Cash, settlement, tradability, account and approval requirements are imposed by
the actual broker/platform, not this skill. Observations about them can inform
advice and the host handoff without creating duplicate local gates.

## Responses and uncertainty

Use the full available response to distinguish submission, acknowledgment, fills,
rejection and unknown state. An empty object or zero process exit does not prove
an order's outcome. Official history and account evidence can clarify it through
the host's workflow. The skill does not manage order retries, locks, ledgers,
cancellation races or state transitions.

Authentication and private identifiers stay within the host/broker environment.
The skill does not contain an OAuth client or an undocumented trading endpoint.
See [execution-handoff.md](execution-handoff.md) and
[host-execution-integration.md](host-execution-integration.md).
