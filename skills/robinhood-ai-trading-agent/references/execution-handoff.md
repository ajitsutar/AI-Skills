# Execution handoff without skill gates

The skill recommends investments, explains research and carries the user's
requested action to the host. It imposes no execution permission or eligibility
system. Spread, volatility, costs, concentration, cash availability, event risk,
strategy evidence and research quality are advisory findings. Do not translate
any of them into a local veto, mandatory acknowledgment, grant, ticket, policy
activation, supervised lease or extra approval.

Preserve instructions and authority already supplied by the user. When they ask
for a trade, use the host's actual connected broker tools with those instructions.
When they ask only for recommendations, deliver recommendations. The host/platform
and broker govern their own capabilities, permissions and transaction behavior;
report an external requirement as external rather than inventing a skill policy.

## What to hand over

Include the requested instrument, side, dollar amount or quantity, order details
and relevant context already given. Preserve an explicit limit instruction. For a
purchase without a specified type, use a market-order handoff preference. Do not
silently round small allocations to whole shares or change dollar instructions
into fixed quantities. Native dollar inputs may be converted to shares at a recent
price; exact spending or a hard final debit is not guaranteed merely by that name.

`scripts/execution_handoff.py` is a pure local formatter with `handoff(payload)`
and a JSON-stdin CLI. It preserves the supplied broker payload in memory and
returns advisory handoff information without contacting a broker. CLI output
redacts private account/authentication fields. It requires no policy file,
ledger, grant, ticket, model output or data threshold. Use real host tool schemas
when mapping an action; do not invent unavailable parameters or tool names.

Research helpers can validate their own inputs, report missing evidence or decline
to calculate an unsupported statistic. Those are mathematical/data limitations,
not execution gates. Likewise, a score or an Eligible/Watch research label is not
a broker permission. A failed volatility fit does not prevent the host handoff.

## Outcome reporting

Report the actual host/broker outcome: proposed, submitted, acknowledged, partial,
filled, rejected or unknown as supported by its evidence. A zero exit code, empty
object or absence from one query does not establish whether an order exists.
Keep full broker evidence private and distinguish reported facts from inference.
The skill does not orchestrate retries, cancellations, reconciliation or background
monitoring; those belong to the actual host/broker workflow. It does not modify
old runtime databases or broker orders during an upgrade.

No extra skill approval is requested. Any actual host/platform/broker confirmation
or unavailable capability is reported plainly as an external requirement.

Execution-time price changes, quote age and research-to-market price drift do not
trigger a skill threshold, pause or repeat approval. Preserve the user's accepted
market-price uncertainty; state the research as-of time without making it a
condition for the host handoff.
