# Broker handoff

The host's connected broker tools perform requested transactions. Before a host
action, follow the selected persistent policy mode: paper stays simulated,
approval requires order approval, and autonomous uses standing authority within
scope. Only an explicit user instruction can change that policy. Research
diagnostics and the pure handoff formatter add no numerical gates or grants.

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
Cash, settlement, tradability and broker-specific account/approval requirements
come from the broker/platform in addition to the selected policy mode. Observations can inform
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

For policy-selected operation, follow [execution modes](execution-modes.md).
Prompts specify the work, not the mode. Under an autonomous policy, an in-scope
authorized action on a permitted host uses real broker tools without another
skill-created per-order ask. A model may clarify missing intent but cannot change
the policy itself. Host restrictions and broker confirmation requirements apply;
no local mode change disables them or permits an alternate execution route.

Each execution task, including each schedule, has a separate policy bound to its
stable `task_id`. New tasks default to paper; no global mode or other task's policy
may supply authority. Verify the current task identity against its file before
actions. Only an explicit user request changes that task's mode. Initialization
creates paper only when absent and preserves an existing valid matching policy;
invalid or wrong-task files are errors. See [per-task policy](execution-modes.md).
