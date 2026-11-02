# User instructions and execution handoff

All requested broker actions use the same host handoff. There is no separate
user-directed bypass and no managed-strategy execution gate. The skill supplies
recommendations, the user's requested order details and advisory findings; it does
not require a grant, ticket, policy, research completion flag, volatility clearance
or local ledger.

Carry forward the user's existing instructions without repeating a skill approval.
A recommendation-only request remains research. Broker/platform requirements and
available order types are external. See [execution-handoff.md](execution-handoff.md)
for payload handling and truthful outcome reporting.
